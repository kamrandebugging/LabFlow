"""Regression tests for Platform Admin defects A2, D6 and D8.

- A2: ordered invoice items with no live sample are exposed as
  ``status=awaiting_collection`` without inventing a Sample status.
- D6: the provisioning credential is never persisted in the audit trail and
  existing rows are scrubbed.
- D8: approval requires an explicit attestation recorded in the audit row.
"""

from __future__ import annotations

import importlib
import uuid
from decimal import Decimal
from typing import cast

import jwt
import pytest
from django.apps import apps as django_apps
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.core.models import Plan, PlatformAudit, Tenant
from apps.platform.platform_jwt import platform_mint_access_token
from apps.results.models import Result
from apps.results.services import AttestationRequiredError, ResultService
from apps.samples.models import Sample
from tests.factories.accounts import StaffUserFactory
from tests.factories.billing import InvoiceFactory, InvoiceItemFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.core import PlatformUserFactory, TenantFactory
from tests.factories.patients import PatientFactory
from tests.factories.results import ResultFactory
from tests.factories.samples import SampleFactory, SampleTestFactory

scrub_temp_passwords = importlib.import_module(
    "apps.core.migrations.0008_scrub_platform_audit_temp_password"
).scrub_temp_passwords


# ---------------------------------------------------------------------------
# A2 — awaiting collection
# ---------------------------------------------------------------------------


def _mint_jwt(staff_id: uuid.UUID, tenant_slug: str, role: str) -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    now = int(timezone.now().timestamp())
    payload = {
        "sub": str(staff_id),
        "tenant": tenant_slug,
        "role": role,
        "typ": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + 3600,
        "iss": "labflow",
        "aud": "labflow-api",
    }
    return str(jwt.encode(payload, str(signing_key), algorithm="HS256"))


def _api_client(tenant: Tenant, staff: StaffUser, role: str = Role.OWNER) -> APIClient:
    client = APIClient()
    client.defaults["HTTP_HOST"] = f"{tenant.slug.replace('_', '-')}.localhost"
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {_mint_jwt(staff.id, tenant.slug, role)}"
    )
    return client


@pytest.mark.django_db
def test_awaiting_collection_returns_ordered_items_without_live_sample(
    tenant_a: Tenant,
) -> None:
    with tenant_context(tenant_a):
        branch = BranchFactory(name="Main")
        staff = cast(StaffUser, StaffUserFactory(role=Role.OWNER, branch=branch))
        patient = PatientFactory(branch=branch, name="Ayesha Khan", mrn="MRN-A2-1")
        invoice = InvoiceFactory(
            patient=patient, branch=branch, status="unpaid"
        )
        awaiting = InvoiceItemFactory(
            invoice=invoice, test=TestFactory(name="CBC", code="CBC")
        )
        collected_item = InvoiceItemFactory(
            invoice=invoice, test=TestFactory(name="LFT", code="LFT")
        )
        sample = SampleFactory(
            invoice=invoice, branch=branch, status=Sample.Status.COLLECTED
        )
        SampleTestFactory(
            sample=sample, test=collected_item.test, invoice_item=collected_item
        )

    client = _api_client(tenant_a, staff)
    resp = client.get("/api/v1/samples?status=awaiting_collection")
    assert resp.status_code == 200, resp.content[:300]
    data = resp.json()
    assert data["total"] == 1
    row = data["results"][0]
    assert row["invoice_item_id"] == str(awaiting.id)
    assert row["invoice_id"] == str(invoice.id)
    assert row["patient_name"] == "Ayesha Khan"
    assert row["patient_mrn"] == "MRN-A2-1"
    assert row["test_name"] == "CBC"
    assert row["status"] == "awaiting_collection"
    assert "ordered_at" in row


@pytest.mark.django_db
def test_awaiting_collection_excludes_cancelled_invoices(tenant_a: Tenant) -> None:
    with tenant_context(tenant_a):
        branch = BranchFactory(name="Main")
        staff = cast(StaffUser, StaffUserFactory(role=Role.OWNER, branch=branch))
        patient = PatientFactory(branch=branch)
        cancelled = InvoiceFactory(
            patient=patient, branch=branch, status="cancelled"
        )
        InvoiceItemFactory(invoice=cancelled, test=TestFactory())

    client = _api_client(tenant_a, staff)
    resp = client.get("/api/v1/samples?status=awaiting_collection")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# D3 — users endpoint never fabricates owner metadata
# ---------------------------------------------------------------------------


def _platform_client() -> APIClient:
    cache.clear()
    platform_user = PlatformUserFactory(totp_enabled=True)
    token, _jti, _exp = platform_mint_access_token(platform_user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_users_endpoint_returns_only_real_owner_metadata() -> None:
    tenant = TenantFactory(
        slug=f"noowner{uuid.uuid4().hex[:6]}",
        name="No Owner Lab",
        owner_name="",
        owner_email="",
        owner_phone="",
    )
    resp = _platform_client().get("/api/v1/platform/users", HTTP_HOST="localhost")
    assert resp.status_code == 200, resp.content[:300]
    data = resp.json()
    row = next(item for item in data["lab_owners"] if item["id"] == str(tenant.id))
    assert row["owner_name"] == ""
    assert row["owner_email"] == ""
    assert row["owner_phone"] == ""
    assert row["last_active"] is None
    # No invitation role exists for these factory users, so no role is
    # inferred from the email address.
    assert all(
        member["role"] == "Platform Operator" for member in data["platform_team"]
    )


# ---------------------------------------------------------------------------
# D6 — credential never written to the audit trail, existing rows scrubbed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_provisioning_audit_never_contains_temp_password() -> None:
    cache.clear()
    plan = Plan.objects.create(
        name="D6 Plan",
        price=Decimal("2999.00"),
        max_branches=1,
        max_staff=5,
        is_active=True,
    )
    platform_user = PlatformUserFactory(totp_enabled=True)
    token, _jti, _exp = platform_mint_access_token(platform_user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    payload = {
        "name": "D6 Diagnostics",
        "slug": f"d6lab{uuid.uuid4().hex[:6]}",
        "plan_id": str(plan.id),
        "owner_name": "Dr. D6",
        "owner_email": "d6@example.com",
        "city": "Lahore",
        "province": "Punjab",
    }
    resp = client.post(
        "/api/v1/platform/tenants", data=payload, format="json", HTTP_HOST="localhost"
    )
    assert resp.status_code == 202, resp.content[:300]
    tenant = Tenant.objects.get(slug=payload["slug"])
    audit = PlatformAudit.objects.get(action="tenant.created", entity_id=tenant.id)
    assert "temp_password" not in audit.after_jsonb
    # The credential still exists on the tenant for the one-time delivery.
    assert tenant.temp_password


@pytest.mark.django_db
def test_scrub_migration_removes_temp_password_from_existing_rows() -> None:
    tenant = TenantFactory(slug=f"scrub{uuid.uuid4().hex[:6]}", name="Scrub Lab")
    with_temp = PlatformAudit.objects.create(
        action="tenant.created",
        entity_type="tenant",
        entity_id=tenant.id,
        after_jsonb={"slug": tenant.slug, "temp_password": "LBF-XXXX-XXX#"},
    )
    without = PlatformAudit.objects.create(
        action="tenant.suspended",
        entity_type="tenant",
        entity_id=tenant.id,
        after_jsonb={"status": "suspended"},
    )

    with connection.schema_editor() as editor:
        scrubbed = scrub_temp_passwords(django_apps, editor)

    assert scrubbed == 1
    with_temp.refresh_from_db()
    without.refresh_from_db()
    assert "temp_password" not in with_temp.after_jsonb
    assert with_temp.after_jsonb["slug"] == tenant.slug
    assert without.after_jsonb == {"status": "suspended"}


# ---------------------------------------------------------------------------
# D8 — approval attestation
# ---------------------------------------------------------------------------


def _entered_result(tenant: Tenant) -> tuple[Result, StaffUser, StaffUser]:
    branch = BranchFactory(name="Main")
    enterer = cast(
        StaffUser, StaffUserFactory(role=Role.TECHNICIAN, branch=branch)
    )
    pathologist = cast(
        StaffUser, StaffUserFactory(role=Role.PATHOLOGIST, branch=branch)
    )
    result = cast(
        Result,
        ResultFactory(entered_by=enterer, sample__branch=branch),
    )
    return result, pathologist, enterer


@pytest.mark.django_db
def test_approval_without_attestation_is_rejected(tenant_a: Tenant) -> None:
    with tenant_context(tenant_a):
        result, pathologist, _ = _entered_result(tenant_a)
        with pytest.raises(AttestationRequiredError) as exc:
            ResultService.approve_result(
                result_id=result.id,
                decision="approved",
                note=None,
                range_override=False,
                actor=pathologist,
            )
        assert exc.value.error_code == "attestation_required"

        mine = Result.objects.get(pk=result.id)
        assert mine.status == Result.Status.ENTERED
        assert not AuditLog.objects.filter(action="result.approved").exists()


@pytest.mark.django_db
def test_approval_with_attestation_records_actor_and_timestamp(
    tenant_a: Tenant,
) -> None:
    with tenant_context(tenant_a):
        result, pathologist, _ = _entered_result(tenant_a)
        payload = ResultService.approve_result(
            result_id=result.id,
            decision="approved",
            note=None,
            range_override=False,
            attestation=True,
            actor=pathologist,
        )
        assert payload["status"] == "approved"
        assert payload["range_attestation"] is True
        assert payload["attested_at"]

        audit = AuditLog.objects.get(action="result.approved", entity_id=result.id)
        assert audit.after_jsonb["range_attestation"] is True
        assert audit.after_jsonb["attested_by"] == str(pathologist.id)
        assert audit.after_jsonb["attested_at"]


@pytest.mark.django_db
def test_rejection_does_not_require_attestation(tenant_a: Tenant) -> None:
    with tenant_context(tenant_a):
        result, pathologist, _ = _entered_result(tenant_a)
        payload = ResultService.approve_result(
            result_id=result.id,
            decision="rejected",
            note="Haemolysed sample, recollect.",
            range_override=False,
            actor=pathologist,
        )
        assert payload["status"] == "rejected"
        assert payload["range_attestation"] is False
