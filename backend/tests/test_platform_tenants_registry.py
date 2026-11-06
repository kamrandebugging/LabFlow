"""Master dashboard Phase 1: tenant registry list/detail (Doc 04 §12.2, §15.1)."""

from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core.models import Subscription, Tenant
from apps.platform.platform_jwt import platform_mint_access_token
from tests.factories.core import (
    PlanFactory,
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)

URL = "/api/v1/platform/tenants"
HOST = "localhost"


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _client() -> APIClient:
    user = PlatformUserFactory(totp_enabled=True)
    token, _jti, _exp = platform_mint_access_token(user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_excludes_the_public_platform_tenant(public_tenant_domain: Any) -> None:
    resp = _client().get(URL, HTTP_HOST=HOST)

    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.json()["tenants"]}
    assert "public" not in slugs


@pytest.mark.django_db
def test_list_filters_by_text_query() -> None:
    TenantFactory(slug="acmelab", name="Acme Diagnostics")
    TenantFactory(slug="zebralab", name="Zebra Labs")

    body = _client().get(f"{URL}?q=acme", HTTP_HOST=HOST).json()

    slugs = [t["slug"] for t in body["tenants"]]
    assert "acmelab" in slugs
    assert "zebralab" not in slugs


@pytest.mark.django_db
def test_list_filters_by_status_and_rejects_unknown_status() -> None:
    TenantFactory(slug="suspendedlab", status=Tenant.Status.SUSPENDED)
    client = _client()

    body = client.get(f"{URL}?status=suspended", HTTP_HOST=HOST).json()
    assert [t["slug"] for t in body["tenants"]] == ["suspendedlab"]

    bad = client.get(f"{URL}?status=nonsense", HTTP_HOST=HOST)
    assert bad.status_code == 422
    assert bad.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_list_paginates_with_an_opaque_cursor() -> None:
    for index in range(3):
        TenantFactory(slug=f"pagelab{index}", name=f"Page Lab {index}")

    client = _client()
    first = client.get(f"{URL}?limit=2", HTTP_HOST=HOST).json()
    assert len(first["tenants"]) == 2
    assert first["next_cursor"]

    second = client.get(
        f"{URL}?limit=2&cursor={first['next_cursor']}", HTTP_HOST=HOST
    ).json()
    assert len(second["tenants"]) == 1
    assert second["next_cursor"] is None

    first_ids = {t["id"] for t in first["tenants"]}
    second_ids = {t["id"] for t in second["tenants"]}
    assert first_ids.isdisjoint(second_ids)


@pytest.mark.django_db
def test_list_rejects_a_malformed_cursor() -> None:
    resp = _client().get(f"{URL}?cursor=not-a-real-cursor", HTTP_HOST=HOST)

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_detail_reports_plan_branches_and_provisioning_state() -> None:
    tenant = TenantFactory()
    plan = PlanFactory(name="Growth", price="9000.00", max_branches=3)
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
    Tenant.objects.filter(id=tenant.id).update(branch_count=2)

    resp = _client().get(f"{URL}/{tenant.id}", HTTP_HOST=HOST)

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan"]["name"] == "Growth"
    assert body["plan"]["price"] == "9000.00"
    assert body["branches_used"] == 2
    assert body["branches_limit"] == 3
    assert body["subscription"]["status"] == "active"
    assert "migration_state" in body
    assert "provisioning" in body
    # No tenant business content ever appears in the payload.
    for forbidden in ("patients", "samples", "reports", "invoices"):
        assert forbidden not in body


@pytest.mark.django_db
def test_detail_404s_for_unknown_tenant() -> None:
    import uuid

    resp = _client().get(f"{URL}/{uuid.uuid4()}", HTTP_HOST=HOST)

    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


# ---------------------------------------------------------------------------
# Branch counter seam (TP-4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_branch_service_keeps_the_public_branch_count_in_sync(
    tenant_a: Any,
) -> None:
    """Branch create/close mirror the counter the platform surface reads."""
    from django_tenants.utils import schema_context

    from apps.branches.services import BranchService
    from tests.factories.staff_user import StaffUserFactory

    with schema_context(tenant_a.schema_name):
        owner = StaffUserFactory(tenant_wide=True)
        branch = BranchService.create_branch(
            owner, {"code": "ZZZ", "name": "Zeta Lab"}, ip="127.0.0.1"
        )

    tenant_a.refresh_from_db()
    assert tenant_a.branch_count == 1

    with schema_context(tenant_a.schema_name):
        BranchService.close_branch(owner, branch.id, ip="127.0.0.1")

    tenant_a.refresh_from_db()
    assert tenant_a.branch_count == 0
