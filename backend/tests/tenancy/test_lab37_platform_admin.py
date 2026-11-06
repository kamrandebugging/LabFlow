"""LAB-37 (KAN-162): Platform admin — tenant registry, lifecycle, audit.

Doc 04 §12 (platform admin surface), §15.1 (endpoint spec).
Verifies: TN-36, TN-37.
"""

import uuid
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.models import Domain, PlatformAudit, PlatformUser, Tenant
from apps.platform.platform_jwt import platform_mint_access_token
from tests.factories import PlatformUserFactory
from tests.factories.core import TenantFactory


def _platform_jwt(user: Any) -> str:
    """Mint a real platform access token (jti/iat/exp are mandatory claims)."""
    token, _jti, _exp = platform_mint_access_token(user.id, "super_admin")
    return token



def _auth_client(user: PlatformUser) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(user)}")
    # Apex host resolves to public schema (config.urls_public) via
    # django-tenants PUBLIC_SCHEMA_URLCONF (Doc 04 §6.1)
    client.defaults["HTTP_HOST"] = "localhost"
    return client


@pytest.fixture
def sa() -> Any:
    return PlatformUserFactory(totp_enabled=True, is_active=True)


@pytest.fixture
def sa_no_totp() -> Any:
    return PlatformUserFactory(totp_enabled=False, is_active=True)


@pytest.fixture
def tenant_active() -> Any:
    t = TenantFactory(status=Tenant.Status.ACTIVE)
    return t


@pytest.fixture
def tenant_suspended() -> Any:
    return TenantFactory(status=Tenant.Status.SUSPENDED)


# ---------------------------------------------------------------------------
# GET /platform/tenants — list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_tenants_requires_auth() -> None:
    client = APIClient()
    client.defaults["HTTP_HOST"] = "localhost"
    resp = client.get("/api/v1/platform/tenants")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_list_tenants_returns_metadata_only(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    """Registry list exposes metadata only — no tenant row content (Doc 04 §12.2)."""
    client = _auth_client(sa)
    resp = client.get("/api/v1/platform/tenants")
    assert resp.status_code == 200
    data = resp.json()
    assert "tenants" in data
    assert len(data["tenants"]) >= 1
    item = data["tenants"][0]
    # Allowed metadata keys
    for key in ("id", "slug", "name", "status", "created_at", "updated_at"):
        assert key in item, f"missing {key}"
    # Forbidden: tenant row content, row counts
    for key in (
        "patients",
        "invoices",
        "results",
        "reports",
        "staff",
        "row_counts",
        "patient_count",
        "settings",
        "audit_logs",
    ):
        assert key not in item, f"leaked {key}"


@pytest.mark.django_db
def test_list_tenants_status_filter(
    sa: PlatformUser, tenant_active: Tenant, tenant_suspended: Tenant
) -> None:
    client = _auth_client(sa)
    resp = client.get("/api/v1/platform/tenants?status=active")
    assert resp.status_code == 200
    for item in resp.json()["tenants"]:
        assert item["status"] == "active"

    resp = client.get("/api/v1/platform/tenants?status=suspended")
    assert resp.status_code == 200
    for item in resp.json()["tenants"]:
        assert item["status"] == "suspended"


@pytest.mark.django_db
def test_list_tenants_invalid_status_filter(sa: PlatformUser) -> None:
    client = _auth_client(sa)
    resp = client.get("/api/v1/platform/tenants?status=bogus")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /platform/tenants/{id} — detail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tenant_detail_404(sa: PlatformUser) -> None:
    client = _auth_client(sa)
    resp = client.get(f"/api/v1/platform/tenants/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.django_db
def test_tenant_detail_has_domains_no_row_counts(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    Domain.objects.create(
        domain=f"{tenant_active.slug}.labflow.test",
        tenant=tenant_active,
        is_primary=True,
    )
    client = _auth_client(sa)
    resp = client.get(f"/api/v1/platform/tenants/{tenant_active.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(tenant_active.id)
    assert data["slug"] == tenant_active.slug
    assert "domains" in data
    assert len(data["domains"]) == 1
    # Schema size from catalogues is allowed (platform machinery, §12.2)
    assert "schema_size_bytes" in data
    # Forbidden: row counts
    for key in ("patient_count", "row_counts", "patients", "invoices"):
        assert key not in data, f"leaked {key}"


# ---------------------------------------------------------------------------
# POST /platform/tenants/{id}/suspend
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_suspend_requires_totp(sa_no_totp: PlatformUser, tenant_active: Tenant) -> None:
    """Writes without TOTP enrolment → 403 totp_required (Doc 04 §12.1)."""
    client = _auth_client(sa_no_totp)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/suspend",
        data={"reason": "Abuse detected"},
        format="json",
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "totp_required"


@pytest.mark.django_db
def test_suspend_requires_reason(sa: PlatformUser, tenant_active: Tenant) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/suspend",
        data={},
        format="json",
    )
    assert resp.status_code == 422


@pytest.mark.django_db
def test_suspend_active_tenant_audited(sa: PlatformUser, tenant_active: Tenant) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/suspend",
        data={"reason": "Payment overdue"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"

    tenant_active.refresh_from_db()
    assert tenant_active.status == Tenant.Status.SUSPENDED

    audit = PlatformAudit.objects.filter(
        entity_type="tenant",
        entity_id=tenant_active.id,
        action="tenant.suspended",
    ).first()
    assert audit is not None
    assert audit.actor_id == sa.id
    assert audit.before_jsonb == {"status": "active"}
    assert audit.after_jsonb is not None
    assert audit.after_jsonb["reason"] == "Payment overdue"


@pytest.mark.django_db
def test_suspend_non_active_returns_409(
    sa: PlatformUser, tenant_suspended: Tenant
) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_suspended.id}/suspend",
        data={"reason": "Again"},
        format="json",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "invalid_state_transition"


# ---------------------------------------------------------------------------
# POST /platform/tenants/{id}/reactivate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reactivate_suspended_tenant_audited(
    sa: PlatformUser, tenant_suspended: Tenant
) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_suspended.id}/reactivate",
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    tenant_suspended.refresh_from_db()
    assert tenant_suspended.status == Tenant.Status.ACTIVE

    audit = PlatformAudit.objects.filter(
        action="tenant.reactivated", entity_id=tenant_suspended.id
    ).first()
    assert audit is not None
    assert audit.actor_id == sa.id


@pytest.mark.django_db
def test_reactivate_non_suspended_returns_409(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/reactivate",
        format="json",
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /platform/tenants/{id}/offboard + complete-offboarding
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_offboard_starts_suspends_and_audits(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/offboard",
        format="json",
    )
    assert resp.status_code == 202
    tenant_active.refresh_from_db()
    assert tenant_active.status == Tenant.Status.SUSPENDED
    assert PlatformAudit.objects.filter(
        action="tenant.offboarding_started", entity_id=tenant_active.id
    ).exists()


@pytest.mark.django_db
def test_offboard_twice_returns_409(sa: PlatformUser, tenant_active: Tenant) -> None:
    client = _auth_client(sa)
    client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/offboard",
        format="json",
    )
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/offboard",
        format="json",
    )
    assert resp.status_code == 409


@pytest.mark.django_db
def test_complete_offboarding_requires_confirm_true(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    client = _auth_client(sa)
    client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/offboard",
        format="json",
    )
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/complete-offboarding",
        data={"confirm_schema_drop": False},
        format="json",
    )
    assert resp.status_code == 422


@pytest.mark.django_db
def test_complete_offboarding_grace_not_elapsed(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    """Schema drop requires 30-day grace unless waived (Doc 04 §15.1)."""
    client = _auth_client(sa)
    client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/offboard",
        format="json",
    )
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/complete-offboarding",
        data={"confirm_schema_drop": True},
        format="json",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "grace_not_elapsed"


@pytest.mark.django_db
def test_complete_offboarding_with_waive(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    client = _auth_client(sa)
    client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/offboard",
        format="json",
    )
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/complete-offboarding",
        data={
            "confirm_schema_drop": True,
            "waive_grace": True,
            "waive_reason": "Test tenant, drop immediately",
        },
        format="json",
    )
    assert resp.status_code == 200
    tenant_active.refresh_from_db()
    assert tenant_active.status == Tenant.Status.DELETED
    audit = PlatformAudit.objects.filter(
        action="tenant.schema_dropped", entity_id=tenant_active.id
    ).first()
    assert audit is not None
    assert audit.after_jsonb is not None
    assert audit.after_jsonb["grace_waived"] is True


@pytest.mark.django_db
def test_complete_offboarding_without_offboard_start_409(
    sa: PlatformUser, tenant_suspended: Tenant
) -> None:
    """Cannot complete offboarding without the offboard step (409)."""
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_suspended.id}/complete-offboarding",
        data={
            "confirm_schema_drop": True,
            "waive_grace": True,
            "waive_reason": "x",
        },
        format="json",
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /platform/tenants/{id}/retry-provisioning
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_retry_provisioning_only_in_provisioning(sa: PlatformUser) -> None:
    prov_tenant = TenantFactory(status=Tenant.Status.PROVISIONING)
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{prov_tenant.id}/retry-provisioning",
        format="json",
    )
    assert resp.status_code == 202
    assert PlatformAudit.objects.filter(
        action="tenant.provisioning_retried", entity_id=prov_tenant.id
    ).exists()


@pytest.mark.django_db
def test_retry_provisioning_active_returns_409(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/retry-provisioning",
        format="json",
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /platform/tenants/{id}/resend-activation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_resend_activation_audited(sa: PlatformUser, tenant_active: Tenant) -> None:
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/resend-activation",
        format="json",
    )
    assert resp.status_code == 202
    assert PlatformAudit.objects.filter(
        action="tenant.activation_resent", entity_id=tenant_active.id
    ).exists()


@pytest.mark.django_db
def test_resend_activation_once_owner_active_409(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    PlatformAudit.objects.create(
        actor_id=sa.id,
        action="tenant.activated",
        entity_type="tenant",
        entity_id=tenant_active.id,
    )
    client = _auth_client(sa)
    resp = client.post(
        f"/api/v1/platform/tenants/{tenant_active.id}/resend-activation",
        format="json",
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /platform/audit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_platform_audit_list_with_filters(
    sa: PlatformUser, tenant_active: Tenant
) -> None:
    PlatformAudit.objects.create(
        actor_id=sa.id,
        action="tenant.suspended",
        entity_type="tenant",
        entity_id=tenant_active.id,
        after_jsonb={"status": "suspended"},
    )
    client = _auth_client(sa)
    resp = client.get("/api/v1/platform/audit?action=tenant.suspended")
    assert resp.status_code == 200
    rows = resp.json()["audit"]
    assert len(rows) >= 1
    assert all(r["action"] == "tenant.suspended" for r in rows)

    resp = client.get("/api/v1/platform/audit?entity_type=tenant")
    assert resp.status_code == 200
    assert len(resp.json()["audit"]) >= 1


@pytest.mark.django_db
def test_platform_audit_list_requires_auth() -> None:
    client = APIClient()
    client.defaults["HTTP_HOST"] = "localhost"
    resp = client.get("/api/v1/platform/audit")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_platform_audit_is_read_only(sa: PlatformUser) -> None:
    """The audit trail is never writable via the API (Doc 04 §12.2)."""
    client = _auth_client(sa)
    resp = client.post(
        "/api/v1/platform/audit",
        data={"action": "fake"},
        format="json",
    )
    assert resp.status_code == 405
