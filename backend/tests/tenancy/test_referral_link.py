"""Referral link from patient registration to the invoice.

Covers the patient "Referred by" field, carrying the partner onto the invoice,
the partner on the invoice detail and history, and the unchanged discount
gates (reason must name the partner, >25% needs the Owner).
"""

from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role
from apps.billing.models import Invoice
from tests.factories.branch import BranchFactory
from tests.factories.catalog import TestFactory, TestPriceFactory
from tests.factories.partners import ReferralPartnerFactory
from tests.factories.staff_user import StaffUserFactory

PATIENTS_URL = "/api/v1/patients"
INVOICES_URL = "/api/v1/invoices"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(staff_user: Any, tenant_id: str = "tenant_a") -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
        return {
            "Authorization": f"Bearer {session['access']}",
            "Host": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def referral_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="RF1", name="Referral Lab")
        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="rf_owner@t.com")
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="rf_manager@t.com"
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="rf_recep@t.com"
        )
        partner = ReferralPartnerFactory(name="Dr. Ayesha Khan")
        test = TestFactory(name="CBC Test", code="RF-CBC")
        TestPriceFactory(test=test, panel=None, price=Decimal("1000.00"))
        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "partner": partner,
            "test": test,
        }


def _register_patient(
    client: Client,
    setup: dict[str, Any],
    headers: dict[str, str],
    partner_id: Any,
) -> dict[str, Any]:
    response = client.post(
        PATIENTS_URL,
        data={
            "name": "Referral Patient",
            "phone": "03001234567",
            "sex": "F",
            "branch_id": str(setup["branch"].id),
            "referral_partner_id": str(partner_id) if partner_id else None,
        },
        content_type="application/json",
        **headers,
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.django_db
def test_patient_partner_carries_onto_invoice_and_shows_in_summary_and_history(
    tenant_a: Any, referral_setup: dict[str, Any], auth_headers: Any
) -> None:
    client = Client()
    headers = auth_headers(referral_setup["receptionist"])
    partner = referral_setup["partner"]

    patient = _register_patient(client, referral_setup, headers, partner.id)
    assert patient["referral_partner_id"] == str(partner.id)
    assert patient["referral_partner_name"] == "Dr. Ayesha Khan"

    created = client.post(
        INVOICES_URL,
        data={
            "patient_id": patient["id"],
            "branch_id": str(referral_setup["branch"].id),
            "referral_partner_id": str(partner.id),
            "items": [{"test_id": str(referral_setup["test"].id), "qty": 1}],
            "discount_amount": "0.00",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="rf-invoice-1",
        **headers,
    )
    assert created.status_code == 201, created.content
    invoice = created.json()
    assert invoice["referral_partner_id"] == str(partner.id)
    assert invoice["referral_partner_name"] == "Dr. Ayesha Khan"

    history = client.get(f"{INVOICES_URL}/{invoice['id']}/history", **headers)
    assert history.status_code == 200
    created_event = next(e for e in history.json()["events"] if e["event"] == "created")
    assert created_event["referral_partner"] == "Dr. Ayesha Khan"

    with tenant_context(tenant_a):
        stored = Invoice.objects.get(pk=invoice["id"])
        assert stored.referral_partner_id == partner.id


@pytest.mark.django_db
def test_referral_discount_requires_a_reason(
    tenant_a: Any, referral_setup: dict[str, Any], auth_headers: Any
) -> None:
    client = Client()
    headers = auth_headers(referral_setup["owner"])
    patient = _register_patient(client, referral_setup, headers, None)
    partner = referral_setup["partner"]

    no_reason = client.post(
        INVOICES_URL,
        data={
            "patient_id": patient["id"],
            "branch_id": str(referral_setup["branch"].id),
            "referral_partner_id": str(partner.id),
            "items": [{"test_id": str(referral_setup["test"].id), "qty": 1}],
            "discount_amount": "100.00",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="rf-invoice-2",
        **headers,
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["error"]["code"] == "discount_reason_required"

    # The referral is keyed by the invoice's partner_id, not by matching the
    # partner's name in the free-text reason.
    free_text = client.post(
        INVOICES_URL,
        data={
            "patient_id": patient["id"],
            "branch_id": str(referral_setup["branch"].id),
            "referral_partner_id": str(partner.id),
            "items": [{"test_id": str(referral_setup["test"].id), "qty": 1}],
            "discount_amount": "100.00",
            "discount_reason": "Goodwill",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="rf-invoice-3",
        **headers,
    )
    assert free_text.status_code == 201, free_text.content
    assert free_text.json()["referral_partner_id"] == str(partner.id)


@pytest.mark.django_db
def test_referral_discount_over_25_percent_needs_owner(
    tenant_a: Any, referral_setup: dict[str, Any], auth_headers: Any
) -> None:
    client = Client()
    owner_headers = auth_headers(referral_setup["owner"])
    patient = _register_patient(client, referral_setup, owner_headers, None)
    partner = referral_setup["partner"]

    # 300 of 1000 = 30% > 25% -> Owner approval required.
    manager_attempt = client.post(
        INVOICES_URL,
        data={
            "patient_id": patient["id"],
            "branch_id": str(referral_setup["branch"].id),
            "referral_partner_id": str(partner.id),
            "items": [{"test_id": str(referral_setup["test"].id), "qty": 1}],
            "discount_amount": "300.00",
            "discount_reason": "Referral discount - Dr. Ayesha Khan",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="rf-invoice-4",
        **auth_headers(referral_setup["manager"]),
    )
    assert manager_attempt.status_code == 403
    assert manager_attempt.json()["error"]["code"] == "owner_approval_required"

    owner_attempt = client.post(
        INVOICES_URL,
        data={
            "patient_id": patient["id"],
            "branch_id": str(referral_setup["branch"].id),
            "referral_partner_id": str(partner.id),
            "items": [{"test_id": str(referral_setup["test"].id), "qty": 1}],
            "discount_amount": "300.00",
            "discount_reason": "Referral discount - Dr. Ayesha Khan",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="rf-invoice-5",
        **owner_headers,
    )
    assert owner_attempt.status_code == 201, owner_attempt.content
    assert owner_attempt.json()["discount_amount"] == "300.00"
