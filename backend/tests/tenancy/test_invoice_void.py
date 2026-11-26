"""Owner-only append-only void path for corrupted PAID invoices."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from django.db.models import Sum
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch
from apps.billing.models import Invoice, InvoiceVoid, Payment
from apps.partners.models import ShareLedgerEntry
from tests.factories.billing import InvoiceFactory, InvoiceItemFactory, PaymentFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.partners import ReferralPartnerFactory, RevenueShareRuleFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

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
def void_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="VD1", name="Void Lab")
        other_branch = BranchFactory(code="VD2", name="Other Void Lab")
        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="vd_owner@t.com")
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="vd_manager@t.com"
        )
        other_manager = StaffUserFactory(
            role=Role.MANAGER, branch=other_branch, email="vd_other_mgr@t.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        StaffBranch.objects.create(
            staff_user=other_manager, branch=other_branch, is_primary=True
        )
        patient = PatientFactory(branch=branch)
        return {
            "branch": branch,
            "other_branch": other_branch,
            "owner": owner,
            "manager": manager,
            "other_manager": other_manager,
            "patient": patient,
        }


def _create_paid_invoice(
    setup: dict[str, Any],
    *,
    amount: str = "1500.00",
    partner: Any = None,
    test_obj: Any = None,
) -> Invoice:
    invoice = InvoiceFactory(
        patient=setup["patient"],
        branch=setup["branch"],
        referral_partner=partner,
        status=Invoice.Status.PAID,
        subtotal=Decimal(amount),
        total=Decimal(amount),
    )
    if test_obj is not None:
        InvoiceItemFactory(
            invoice=invoice,
            test=test_obj,
            unit_price=Decimal(amount),
            quantity=1,
            line_total=Decimal(amount),
        )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.PAYMENT,
        method=Payment.Method.CASH,
        amount=Decimal(amount),
        received_by=setup["owner"],
        business_date=timezone.localdate(),
    )
    return cast(Invoice, invoice)


@pytest.mark.django_db
def test_owner_can_void_paid_invoice_append_only_with_ledger_and_audit(
    tenant_a: Any, void_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Owner voids a corrupted PAID invoice: append-only, compensating ledger, audit."""
    client = Client()
    headers = auth_headers(void_setup["owner"])

    with tenant_context(tenant_a):
        partner = ReferralPartnerFactory(is_active=True, name="Void Partner")
        Rule_test = TestFactory(category="Biochemistry", name="LFT")
        RevenueShareRuleFactory(
            referral_partner=partner,
            test_category="Biochemistry",
            branch=void_setup["branch"],
            percent=Decimal("10.00"),
            effective_from=date.today() - timedelta(days=5),
        )
        invoice = _create_paid_invoice(
            void_setup, amount="2000.00", partner=partner, test_obj=Rule_test
        )
        from apps.partners.services import record_share_entry

        payment = invoice.payments.first()
        assert payment is not None
        accrual = record_share_entry(payment)
        assert accrual is not None
        assert accrual.amount == Decimal("200.00")
        invoice_id = invoice.id
        inv_num = f"INV-{str(invoice_id)[:8].upper()}"

    resp = client.post(
        f"{INVOICES_URL}/{inv_num}/void",
        data={"reason": "Corrupted duplicate billing INV-89521878"},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "voided"

    with tenant_context(tenant_a):
        invoice = Invoice.objects.get(pk=invoice_id)
        assert invoice.status == Invoice.Status.VOIDED
        # Original invoice money & payments untouched
        assert invoice.total == Decimal("2000.00")
        assert invoice.payments.count() == 1

        void_rec = InvoiceVoid.objects.get(invoice=invoice)
        assert void_rec.voided_by_id == void_setup["owner"].id
        assert void_rec.reason == "Corrupted duplicate billing INV-89521878"
        assert void_rec.reversed_methods == {"cash": "2000.00"}

        # Compensating ledger entry zeroes partner share
        ledger_sum = ShareLedgerEntry.objects.filter(
            referral_partner=partner
        ).aggregate(total=Sum("amount"))["total"]
        assert ledger_sum == Decimal("0.00")
        assert ShareLedgerEntry.objects.filter(invoice_void=void_rec).exists()

        # Audit row written
        audit = AuditLog.objects.filter(
            action="invoice.voided", entity_id=invoice.id
        ).first()
        assert audit is not None
        assert audit.actor_id == void_setup["owner"].id
        assert audit.after_jsonb is not None
        assert audit.after_jsonb["reason"] == "Corrupted duplicate billing INV-89521878"

    # Detail & history reflect voided state
    detail = client.get(f"{INVOICES_URL}/{invoice_id}", headers=headers).json()
    assert detail["status"] == "voided"
    assert detail["net_revenue"] == "0.00"
    assert detail["balance"] == "0.00"
    assert detail["void_reason"] == "Corrupted duplicate billing INV-89521878"

    history = client.get(f"{INVOICES_URL}/{invoice_id}/history", headers=headers).json()
    assert any(e["event"] == "voided" for e in history["events"])

    # Voided invoice accepts no further payment, refund, credit note, or second void
    pay_resp = client.post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "100.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="vd-pay-1",
        headers=headers,
    )
    assert pay_resp.status_code == 409

    ref_resp = client.post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "100.00",
            "refund_reason": "After void",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="vd-ref-1",
        headers=headers,
    )
    assert ref_resp.status_code == 409

    cn_resp = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "2000.00", "reason": "After void"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="vd-cn-1",
        headers=headers,
    )
    assert cn_resp.status_code == 409

    second_void = client.post(
        f"{INVOICES_URL}/{invoice_id}/void",
        data={"reason": "Second void"},
        content_type="application/json",
        headers=headers,
    )
    assert second_void.status_code == 409


@pytest.mark.django_db
def test_void_guards_non_owner_missing_reason_and_unpaid(
    tenant_a: Any, void_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Non-Owner -> 403; missing reason -> 422; unpaid -> 409; missing -> 404."""
    client = Client()
    owner_headers = auth_headers(void_setup["owner"])
    mgr_headers = auth_headers(void_setup["manager"])

    with tenant_context(tenant_a):
        paid_inv = _create_paid_invoice(void_setup, amount="1000.00")
        unpaid_inv = InvoiceFactory(
            patient=void_setup["patient"],
            branch=void_setup["branch"],
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        paid_id = paid_inv.id
        unpaid_id = unpaid_inv.id

    # Non-Owner -> 403
    non_owner = client.post(
        f"{INVOICES_URL}/{paid_id}/void",
        data={"reason": "Manager attempt"},
        content_type="application/json",
        headers=mgr_headers,
    )
    assert non_owner.status_code == 403

    # Missing/blank reason -> 422
    no_reason = client.post(
        f"{INVOICES_URL}/{paid_id}/void",
        data={"reason": "   "},
        content_type="application/json",
        headers=owner_headers,
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["error"]["code"] == "void_reason_required"

    # Unpaid invoice -> 409
    unpaid_resp = client.post(
        f"{INVOICES_URL}/{unpaid_id}/void",
        data={"reason": "Cannot void unpaid"},
        content_type="application/json",
        headers=owner_headers,
    )
    assert unpaid_resp.status_code == 409

    # Missing invoice -> 404
    missing_resp = client.post(
        f"{INVOICES_URL}/00000000-0000-0000-0000-000000000000/void",
        data={"reason": "Missing"},
        content_type="application/json",
        headers=owner_headers,
    )
    assert missing_resp.status_code == 404
