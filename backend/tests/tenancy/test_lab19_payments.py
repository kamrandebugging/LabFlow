"""LAB-19 Test Suite: Payments recording (Doc 03 §5.3, §6.4, KAN-130).

Covers (original LAB-21):
- T-18: partial payment → status partial; full payment → paid; BL-6 derivation.
- T-21: Idempotency-Key required; replay → 200 original; reused key + new
  payload → 409 idempotency_key_reused.
- T-36: refund rules — refund_exceeds_payments → 422; overpayment → 422;
  refund ceiling (manager ≤ 5000, owner above) → 403 owner_approval_required;
  refund by receptionist → 403; reference required → 422.
- BL-5: payments append-only (no update/delete path).
- BL-7: refunded status derivation; cancelled invoice → 409.
- BL-10: reference required for non-cash + all refunds.
- BL-V1: money as Decimal strings (money_must_be_string).
- Audit: payment.recorded / payment.refunded rows in the same transaction.
- Tenant scoping: unknown invoice id → 404, not 403.
"""

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.models import Invoice, Payment
from apps.billing.services import BillingService
from tests.factories.branch import BranchFactory
from tests.factories.catalog import PanelFactory, TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
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
            role=Role.OWNER, branch=None, email="pay_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="pay_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="pay_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="pay_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )

        patient = PatientFactory(branch=branch)

        test_a = TestFactory(name="CBC Test", code="CBC001")
        TestPriceFactory(test=test_a, panel=None, price=Decimal("1500.00"))
        test_b = TestFactory(name="Lipid Test", code="LIP001")
        TestPriceFactory(test=test_b, panel=None, price=Decimal("800.00"))
        panel = PanelFactory(name="Basic Panel", code="PNL001")
        TestPriceFactory(test=None, panel=panel, price=Decimal("2500.00"))

        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "patient": patient,
            "test_a": test_a,
            "test_b": test_b,
            "panel": panel,
        }


def _make_invoice(
    tenant: Any,
    setup: dict[str, Any],
    items: list[dict[str, Any]] | None = None,
    discount: str = "0.00",
    discount_reason: str | None = None,
    actor_key: str = "manager",
    key_suffix: str = "inv",
) -> Invoice:
    """Create an invoice via the service (setup helper, not the API)."""
    if items is None:
        items = [
            {"test_id": str(setup["test_a"].id), "qty": 1},
            {"test_id": str(setup["test_b"].id), "qty": 1},
        ]
    with tenant_context(tenant):
        invoice, _ = BillingService.create_invoice(
            patient_id=setup["patient"].id,
            branch_id=setup["branch"].id,
            referral_partner_id=None,
            items=items,
            discount_amount=Decimal(discount),
            discount_reason=discount_reason,
            idempotency_key=f"{key_suffix}-{uuid.uuid4().hex[:8]}",
            actor=setup[actor_key],
        )
    return invoice


def _fresh_status(tenant: Any, invoice: Invoice) -> str:
    """Reload the invoice inside the tenant schema and return its status."""
    with tenant_context(tenant):
        invoice.refresh_from_db()
    return str(invoice.status)


def _post_payment(
    client: Client,
    headers: dict[str, str],
    invoice_id: uuid.UUID,
    body: dict[str, Any],
    idem_key: str | None = "pay-key-001",
) -> Any:
    extra = dict(headers)
    if idem_key is not None:
        extra["Idempotency-Key"] = idem_key
    return client.post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data=json.dumps(body),
        content_type="application/json",
        headers=extra,
    )


def _pay_body(
    kind: str = "payment",
    method: str = "cash",
    amount: str = "1000.00",
    reference: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {"kind": kind, "method": method, "amount": amount}
    if reference is not None:
        body["reference"] = reference
    body.update(overrides)
    return body


@pytest.mark.django_db
class TestPartialAndFullPayments:
    """T-18: BL-6 status derivation from payment rows."""

    def test_partial_payment_sets_status_partial(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t18a")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="1000.00"),
            idem_key="t18a-001",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["amount"] == "1000.00"
        assert _fresh_status(tenant_a, invoice) == "partial"

    def test_full_payment_sets_status_paid(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t18b")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="2300.00"),
            idem_key="t18b-001",
        )
        assert resp.status_code == 201
        assert _fresh_status(tenant_a, invoice) == "paid"

    def test_multiple_partial_payments_accumulate(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t18c")
        headers = auth_headers(billing_setup["receptionist"])
        r1 = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="1000.00"),
            idem_key="t18c-001",
        )
        assert r1.status_code == 201
        assert _fresh_status(tenant_a, invoice) == "partial"
        r2 = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="1300.00"),
            idem_key="t18c-002",
        )
        assert r2.status_code == 201
        assert _fresh_status(tenant_a, invoice) == "paid"

    def test_non_cash_payment_without_reference_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t18d")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(method="easypaisa", amount="500.00"),
            idem_key="t18d-001",
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "reference_required"

    def test_non_cash_payment_with_reference_ok(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t18e")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(method="easypaisa", amount="500.00", reference="EP-TRX-123"),
            idem_key="t18e-001",
        )
        assert resp.status_code == 201
        assert resp.json()["reference"] == "EP-TRX-123"

    def test_payment_by_technician_forbidden(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t18f")
        headers = auth_headers(billing_setup["technician"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="500.00"),
            idem_key="t18f-001",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestPaymentIdempotency:
    """T-21: Idempotency-Key on payment writes."""

    def test_missing_idempotency_key_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t21a")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="500.00"),
            idem_key=None,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "idempotency_key_required"

    def test_replay_same_key_and_payload_returns_200_original(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t21b")
        headers = auth_headers(billing_setup["receptionist"])
        client = Client()
        r1 = _post_payment(
            client,
            headers,
            invoice.id,
            _pay_body(amount="500.00"),
            idem_key="t21b-replay",
        )
        assert r1.status_code == 201
        r2 = _post_payment(
            client,
            headers,
            invoice.id,
            _pay_body(amount="500.00"),
            idem_key="t21b-replay",
        )
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]
        with tenant_context(tenant_a):
            assert Payment.objects.filter(invoice_id=invoice.id).count() == 1

    def test_reused_key_with_different_payload_409(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t21c")
        headers = auth_headers(billing_setup["receptionist"])
        client = Client()
        r1 = _post_payment(
            client,
            headers,
            invoice.id,
            _pay_body(amount="500.00"),
            idem_key="t21c-reused",
        )
        assert r1.status_code == 201
        r2 = _post_payment(
            client,
            headers,
            invoice.id,
            _pay_body(amount="600.00"),
            idem_key="t21c-reused",
        )
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "idempotency_key_reused"


@pytest.mark.django_db
class TestRefundRules:
    """T-36: BL-7 refund guards + ceiling + RBAC."""

    def test_refund_exceeding_payments_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t36a")
        headers = auth_headers(billing_setup["manager"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(kind="refund", amount="500.00", reference="rsn-001"),
            idem_key="t36a-001",
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "refund_exceeds_payments"

    def test_overpayment_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t36b")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="3000.00"),
            idem_key="t36b-001",
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "overpayment"

    def test_refund_by_receptionist_forbidden(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t36c")
        rec_headers = auth_headers(billing_setup["receptionist"])
        pay = _post_payment(
            Client(),
            rec_headers,
            invoice.id,
            _pay_body(amount="1000.00"),
            idem_key="t36c-pay",
        )
        assert pay.status_code == 201
        resp = _post_payment(
            Client(),
            rec_headers,
            invoice.id,
            _pay_body(kind="refund", amount="200.00", reference="rsn-002"),
            idem_key="t36c-ref",
        )
        assert resp.status_code == 403

    def test_refund_requires_reference(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t36d")
        headers = auth_headers(billing_setup["manager"])
        pay = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="1000.00"),
            idem_key="t36d-pay",
        )
        assert pay.status_code == 201
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(kind="refund", amount="200.00"),
            idem_key="t36d-ref",
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "reference_required"

    def test_manager_refund_above_5000_needs_owner(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        items = [
            {"test_id": str(billing_setup["test_a"].id), "qty": 4},  # 6000
            {"test_id": str(billing_setup["test_b"].id), "qty": 1},  # 800
            {"panel_id": str(billing_setup["panel"].id), "qty": 1},  # 2500
        ]
        invoice = _make_invoice(tenant_a, billing_setup, items=items, key_suffix="t36e")
        assert invoice.total == Decimal("9300.00")
        mgr_headers = auth_headers(billing_setup["manager"])
        pay = _post_payment(
            Client(),
            mgr_headers,
            invoice.id,
            _pay_body(amount="9300.00"),
            idem_key="t36e-pay",
        )
        assert pay.status_code == 201
        resp = _post_payment(
            Client(),
            mgr_headers,
            invoice.id,
            _pay_body(kind="refund", amount="6000.00", reference="rsn-003"),
            idem_key="t36e-ref",
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "owner_approval_required"

    def test_owner_refund_above_5000_ok(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        items = [
            {"test_id": str(billing_setup["test_a"].id), "qty": 4},
            {"test_id": str(billing_setup["test_b"].id), "qty": 1},
            {"panel_id": str(billing_setup["panel"].id), "qty": 1},
        ]
        invoice = _make_invoice(tenant_a, billing_setup, items=items, key_suffix="t36f")
        mgr_headers = auth_headers(billing_setup["manager"])
        pay = _post_payment(
            Client(),
            mgr_headers,
            invoice.id,
            _pay_body(amount="9300.00"),
            idem_key="t36f-pay",
        )
        assert pay.status_code == 201
        own_headers = auth_headers(billing_setup["owner"])
        resp = _post_payment(
            Client(),
            own_headers,
            invoice.id,
            _pay_body(kind="refund", amount="6000.00", reference="rsn-004"),
            idem_key="t36f-ref",
        )
        assert resp.status_code == 201
        assert _fresh_status(tenant_a, invoice) == "partial"  # net 3300 < 9300

    def test_full_refund_sets_status_refunded(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t36g")
        headers = auth_headers(billing_setup["manager"])
        pay = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="2300.00"),
            idem_key="t36g-pay",
        )
        assert pay.status_code == 201
        assert _fresh_status(tenant_a, invoice) == "paid"
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(kind="refund", amount="2300.00", reference="rsn-005"),
            idem_key="t36g-ref",
        )
        assert resp.status_code == 201
        assert _fresh_status(tenant_a, invoice) == "refunded"

    def test_partial_refund_keeps_partial(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="t36h")
        headers = auth_headers(billing_setup["manager"])
        pay = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="2300.00"),
            idem_key="t36h-pay",
        )
        assert pay.status_code == 201
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(kind="refund", amount="500.00", reference="rsn-006"),
            idem_key="t36h-ref",
        )
        assert resp.status_code == 201
        assert _fresh_status(tenant_a, invoice) == "partial"  # net 1800 < 2300


@pytest.mark.django_db
class TestPaymentGuards:
    """BL-5 append-only, cancelled invoices, BL-V1, audit, scoping."""

    def test_payments_append_only_no_update_or_delete_route(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="g1")
        headers = auth_headers(billing_setup["receptionist"])
        client = Client()
        base = f"{INVOICES_URL}/{invoice.id}/payments"
        assert client.put(base, headers=headers).status_code == 405
        assert client.patch(base, headers=headers).status_code == 405
        assert client.delete(base, headers=headers).status_code == 405

    def test_payment_on_cancelled_invoice_409(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="g2")
        with tenant_context(tenant_a):
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=["status"])
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="500.00"),
            idem_key="g2-001",
        )
        assert resp.status_code == 409

    def test_money_as_json_number_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="g3")
        headers = auth_headers(billing_setup["receptionist"])
        body = {"kind": "payment", "method": "cash", "amount": 100.00}
        resp = _post_payment(Client(), headers, invoice.id, body, idem_key="g3-001")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "money_must_be_string"

    def test_unknown_invoice_id_404(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        _make_invoice(tenant_a, billing_setup, key_suffix="g4")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            uuid.uuid4(),
            _pay_body(amount="500.00"),
            idem_key="g4-001",
        )
        assert resp.status_code == 404

    def test_unknown_fields_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="g5")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="500.00", bogus_field="x"),
            idem_key="g5-001",
        )
        assert resp.status_code == 422

    def test_payment_on_zero_total_invoice_is_overpayment(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(
            tenant_a,
            billing_setup,
            discount="2300.00",
            discount_reason="charity case",
            # LAB-49 Phase 2.3: a 100% discount requires the Owner.
            actor_key="owner",
            key_suffix="g6",
        )
        assert invoice.status == "paid"
        assert invoice.total == Decimal("0.00")
        headers = auth_headers(billing_setup["receptionist"])
        resp = _post_payment(
            Client(),
            headers,
            invoice.id,
            _pay_body(amount="100.00"),
            idem_key="g6-001",
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "overpayment"

    def test_audit_rows_written_for_payment_and_refund(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        invoice = _make_invoice(tenant_a, billing_setup, key_suffix="g7")
        headers = auth_headers(billing_setup["manager"])
        client = Client()
        pay = _post_payment(
            client,
            headers,
            invoice.id,
            _pay_body(amount="1000.00"),
            idem_key="g7-pay",
        )
        assert pay.status_code == 201
        ref = _post_payment(
            client,
            headers,
            invoice.id,
            _pay_body(kind="refund", amount="200.00", reference="rsn-007"),
            idem_key="g7-ref",
        )
        assert ref.status_code == 201
        with tenant_context(tenant_a):
            pay_row = AuditLog.objects.get(
                action="payment.recorded",
                entity_id=uuid.UUID(pay.json()["id"]),
            )
            assert pay_row.actor_id == billing_setup["manager"].id
            after = pay_row.after_jsonb
            assert isinstance(after, dict)
            assert after["event"] == "billing.payment_recorded"
            assert after["kind"] == "payment"
            ref_row = AuditLog.objects.get(
                action="payment.refunded",
                entity_id=uuid.UUID(ref.json()["id"]),
            )
            after_ref = ref_row.after_jsonb
            assert isinstance(after_ref, dict)
            assert after_ref["event"] == "billing.payment_recorded"
            assert after_ref["kind"] == "refund"
