"""LAB-20 Test Suite: Billing adjustments — cancel + reads (Doc 03 §5.3 BL-8, §6.4,
KAN-132).

Covers (original LAB-22):
- T-23: cancel happy path; refuses once money exists or sample collected.
- POST /invoices/{id}/cancel — reason required (422); unpaid-only + no
  collected sample (409 invalid_state_transition); repeat cancel → 409;
  RBAC (403 for Technician); 404 out of scope.
- GET /invoices — cursor pagination (limit/cursor/next_cursor), filters
  (status, patient_id, branch_id, created_after/created_before), invalid
  enum → 422, unknown filter ignored.
- GET /invoices/{id} — detail with items, payments, computed net_paid; 404.
- Audit: invoice.cancelled row in the same transaction.
"""

import base64
import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.services import BillingService, PaymentService
from tests.factories.branch import BranchFactory
from tests.factories.catalog import TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
from tests.factories.samples import SampleFactory
from tests.factories.staff_user import StaffUserFactory

INVOICES_URL = "/api/v1/invoices"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(
            user=staff_user,
            tenant_id=tenant_id,
        )
        return {
            "Authorization": f"Bearer {session['access']}",
            "Host": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def billing_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="cancel_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="cancel_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="cancel_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="cancel_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )

        patient = PatientFactory(branch=branch)
        test_a = TestFactory(name="CBC Test", code="CBC001")
        TestPriceFactory(test=test_a, panel=None, price=Decimal("1500.00"))

        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "patient": patient,
            "test_a": test_a,
        }


def _make_invoice(setup: dict[str, Any], actor: Any, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "patient_id": setup["patient"].id,
        "branch_id": setup["branch"].id,
        "referral_partner_id": None,
        "items": [{"test_id": setup["test_a"].id, "qty": 1}],
        "discount_amount": Decimal("0.00"),
        "discount_reason": None,
    }
    body.update(overrides)
    invoice, _ = BillingService.create_invoice(
        patient_id=body["patient_id"],
        branch_id=body["branch_id"],
        referral_partner_id=None,
        items=body["items"],
        discount_amount=body["discount_amount"],
        discount_reason=None,
        idempotency_key=f"lab20-{uuid.uuid4()}",
        actor=actor,
    )
    return invoice


def _cancel(
    client: Client,
    headers: dict[str, str],
    invoice_id: uuid.UUID,
    body: dict[str, Any] | None = None,
) -> Any:
    extra = dict(headers)
    return client.post(
        f"{INVOICES_URL}/{invoice_id}/cancel",
        data=json.dumps(body if body is not None else {}),
        content_type="application/json",
        headers=extra,
    )


def _pay(setup: dict[str, Any], actor: Any, invoice: Any, amount: str) -> Any:
    payment, _ = PaymentService.record_payment(
        invoice_id=invoice.id,
        kind="payment",
        method="cash",
        amount=Decimal(amount),
        reference=None,
        idempotency_key=f"lab20-pay-{uuid.uuid4()}",
        actor=actor,
    )
    return payment


@pytest.mark.django_db
class TestInvoiceCancel:
    """T-23: cancel rules (BL-8)."""

    def test_cancel_happy_path(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            resp = _cancel(Client(), headers, invoice.id, {"reason": "duplicate entry"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "cancelled"
            assert data["id"] == str(invoice.id)
            row = AuditLog.objects.get(action="invoice.cancelled", entity_id=invoice.id)
            assert row.actor_id == billing_setup["manager"].id

    def test_cancel_missing_reason_422(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            resp = _cancel(Client(), headers, invoice.id, {})
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "cancel_reason_required"

    def test_cancel_with_payment_refused_409(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            _pay(billing_setup, billing_setup["receptionist"], invoice, "500.00")
            headers = auth_headers(billing_setup["manager"])
            resp = _cancel(Client(), headers, invoice.id, {"reason": "changed mind"})
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_cancel_with_collected_sample_refused_409(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            SampleFactory(invoice=invoice, branch=billing_setup["branch"])
            headers = auth_headers(billing_setup["manager"])
            resp = _cancel(Client(), headers, invoice.id, {"reason": "too late"})
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_cancel_already_cancelled_409(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            first = _cancel(Client(), headers, invoice.id, {"reason": "oops"})
            assert first.status_code == 200
            second = _cancel(Client(), headers, invoice.id, {"reason": "oops again"})
            assert second.status_code == 409
            assert second.json()["error"]["code"] == "invalid_state_transition"

    def test_cancel_by_technician_403(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["technician"])
            resp = _cancel(Client(), headers, invoice.id, {"reason": "nope"})
            assert resp.status_code == 403

    def test_cancel_not_found_404(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(billing_setup["manager"])
            resp = _cancel(Client(), headers, uuid.uuid4(), {"reason": "ghost"})
            assert resp.status_code == 404

    def test_cancel_unknown_field_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            resp = _cancel(Client(), headers, invoice.id, {"reason": "x", "bogus": 1})
            assert resp.status_code == 422


@pytest.mark.django_db
class TestInvoiceList:
    """GET /invoices — cursor pagination + filters."""

    def _list(self, client: Client, headers: dict[str, str], qs: str = "") -> Any:
        return client.get(f"{INVOICES_URL}{qs}", headers=headers)

    def test_pagination_cursor(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            for _ in range(3):
                _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["receptionist"])
            page1 = self._list(Client(), headers, "?limit=2")
            assert page1.status_code == 200
            d1 = page1.json()
            assert len(d1["results"]) == 2
            assert d1["next_cursor"] is not None
            page2 = self._list(
                Client(), headers, f"?limit=2&cursor={d1['next_cursor']}"
            )
            d2 = page2.json()
            assert len(d2["results"]) == 1
            assert d2["next_cursor"] is None
            # stable ordering: no overlap, no gaps
            ids1 = {r["id"] for r in d1["results"]}
            ids2 = {r["id"] for r in d2["results"]}
            assert not ids1 & ids2

    def test_filter_status(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            inv = _make_invoice(billing_setup, billing_setup["manager"])
            _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            _cancel(Client(), headers, inv.id, {"reason": "filter me"})
            resp = self._list(Client(), headers, "?status=cancelled")
            data = resp.json()
            assert len(data["results"]) == 1
            assert data["results"][0]["id"] == str(inv.id)

    def test_filter_invalid_status_422(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(billing_setup["manager"])
            resp = self._list(Client(), headers, "?status=bogus")
            assert resp.status_code == 422

    def test_filter_patient_and_branch(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            inv = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            resp = self._list(Client(), headers, f"?patient_id={inv.patient_id}")
            assert len(resp.json()["results"]) == 1
            resp = self._list(Client(), headers, f"?branch_id={inv.branch_id}")
            assert len(resp.json()["results"]) == 1

    def test_unknown_filter_ignored(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            resp = self._list(Client(), headers, "?nonsense=1")
            assert resp.status_code == 200
            assert len(resp.json()["results"]) == 1

    def test_limit_capped_at_200(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            resp = self._list(Client(), headers, "?limit=500")
            assert resp.status_code == 200
            assert len(resp.json()["results"]) == 1

    def test_technician_may_list(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["technician"])
            resp = self._list(Client(), headers)
            assert resp.status_code == 200


@pytest.mark.django_db
class TestInvoiceDetail:
    """GET /invoices/{id} — items + payments + net_paid."""

    def test_detail_net_paid(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            _pay(billing_setup, billing_setup["receptionist"], invoice, "1000.00")
            headers = auth_headers(billing_setup["manager"])
            resp = Client().get(f"{INVOICES_URL}/{invoice.id}", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == str(invoice.id)
            assert data["net_paid"] == "1000.00"
            assert data["status"] == "partial"
            assert len(data["items"]) == 1
            assert data["items"][0]["description"] == "CBC Test"
            assert len(data["payments"]) == 1
            assert data["payments"][0]["amount"] == "1000.00"

    def test_detail_not_found_404(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(billing_setup["manager"])
            resp = Client().get(f"{INVOICES_URL}/{uuid.uuid4()}", headers=headers)
            assert resp.status_code == 404


@pytest.mark.django_db
class TestA1TechnicianInvoiceReadOnly:
    """Owner decision 2026-11-13: Technician = invoice read-only, no writes."""

    def test_technician_can_read_invoice_list(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["technician"])
            resp = Client().get(INVOICES_URL, headers=headers)
            assert resp.status_code == 200
            assert len(resp.json()["results"]) == 1

    def test_technician_can_read_invoice_detail(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["technician"])
            resp = Client().get(f"{INVOICES_URL}/{invoice.id}", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["id"] == str(invoice.id)

    def test_technician_cannot_create_invoice(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(billing_setup["technician"])
            resp = Client().post(
                INVOICES_URL,
                data=json.dumps({}),
                content_type="application/json",
                headers=headers,
            )
            assert resp.status_code == 403

    def test_technician_cannot_record_payment(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["technician"])
            resp = Client().post(
                f"{INVOICES_URL}/{invoice.id}/payments",
                data=json.dumps(
                    {"kind": "payment", "method": "cash", "amount": "1.00"}
                ),
                content_type="application/json",
                headers=headers,
            )
            assert resp.status_code == 403

    def test_technician_cannot_cancel_invoice(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["technician"])
            resp = _cancel(Client(), headers, invoice.id, {"reason": "not allowed"})
            assert resp.status_code == 403

    def test_technician_cannot_read_settlements(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(billing_setup["technician"])
            resp = Client().get("/api/v1/settlements", headers=headers)
            assert resp.status_code == 403

    def test_technician_cannot_read_partner_ledger(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(billing_setup["technician"])
            resp = Client().get("/api/v1/referral-partners/ledger", headers=headers)
            assert resp.status_code == 403

    def test_reception_and_manager_reads_still_pass(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            invoice = _make_invoice(billing_setup, billing_setup["manager"])
            for role in ("receptionist", "manager"):
                headers = auth_headers(billing_setup[role])
                list_resp = Client().get(INVOICES_URL, headers=headers)
                detail_resp = Client().get(
                    f"{INVOICES_URL}/{invoice.id}", headers=headers
                )
                assert list_resp.status_code == 200
                assert detail_resp.status_code == 200


def _decode_cursor(cursor: str) -> dict[str, Any]:
    raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
    return json.loads(raw)


@pytest.mark.django_db
class TestCursorShape:
    """Cursor is opaque but well-formed (created_at + id)."""

    def test_cursor_encodes_position(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        with tenant_context(tenant_a):
            for _ in range(2):
                _make_invoice(billing_setup, billing_setup["manager"])
            headers = auth_headers(billing_setup["manager"])
            resp = Client().get(f"{INVOICES_URL}?limit=1", headers=headers)
            cursor = resp.json()["next_cursor"]
            assert cursor is not None
            payload = _decode_cursor(cursor)
            assert "created_at" in payload and "id" in payload
