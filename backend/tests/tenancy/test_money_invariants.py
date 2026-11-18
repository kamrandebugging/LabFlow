"""Money invariants: concurrency, DB-level idempotency, caps, scope, day lock."""

import threading
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role, StaffBranch
from apps.billing.models import CreditNote, DayClose, Invoice, Payment
from apps.billing.services import (
    BillingError,
    CreditNoteService,
    PaymentService,
)
from tests.factories.billing import InvoiceFactory, PaymentFactory
from tests.factories.branch import BranchFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

INVOICES_URL = "/api/v1/invoices"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(staff_user: Any) -> dict[str, str]:
        session = AuthService.create_session(user=staff_user, tenant_id="tenant_a")
        return {
            "Authorization": f"Bearer {session['access']}",
            "Host": "tenant-a.localhost",
        }

    return _make_headers


@pytest.fixture
def mi_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MI1", name="Money Lab")
        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="mi_owner@t.com")
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="mi_recep@t.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        patient = PatientFactory(branch=branch)
        return {
            "tenant": tenant_a,
            "branch": branch,
            "owner": owner,
            "receptionist": receptionist,
            "patient": patient,
        }


def _paid_invoice(setup: dict[str, Any], amount: str = "1000.00") -> Any:
    invoice = InvoiceFactory(
        patient=setup["patient"],
        branch=setup["branch"],
        status=Invoice.Status.PAID,
        subtotal=Decimal(amount),
        total=Decimal(amount),
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.PAYMENT,
        method=Payment.Method.CASH,
        amount=Decimal(amount),
        received_by=setup["owner"],
    )
    return invoice


@pytest.mark.django_db(transaction=True)
def test_concurrent_refund_and_credit_note_cannot_go_negative(
    mi_setup: dict[str, Any],
) -> None:
    """A refund and a credit note racing on one invoice move money once."""
    tenant = mi_setup["tenant"]
    with tenant_context(tenant):
        invoice_id = _paid_invoice(mi_setup, "1000.00").id
        owner_id = mi_setup["owner"].id

    results: dict[str, str] = {}

    def refund() -> None:
        try:
            with tenant_context(tenant):
                from apps.accounts.models import StaffUser

                actor = StaffUser.objects.get(pk=owner_id)
                PaymentService.record_payment(
                    invoice_id=invoice_id,
                    kind=Payment.Kind.REFUND,
                    method=Payment.Method.CASH,
                    amount=Decimal("600.00"),
                    reference="concurrent refund",
                    idempotency_key="mi-conc-refund-1",
                    actor=actor,
                )
                results["refund"] = "ok"
        except BillingError as exc:
            results["refund"] = exc.error_code
        finally:
            connection.close()

    def credit_note() -> None:
        try:
            with tenant_context(tenant):
                from apps.accounts.models import StaffUser

                actor = StaffUser.objects.get(pk=owner_id)
                CreditNoteService.issue(
                    invoice_id=invoice_id,
                    amount=Decimal("1000.00"),
                    reason="concurrent note",
                    method=Payment.Method.CASH,
                    idempotency_key="mi-conc-note-1",
                    actor=actor,
                )
                results["credit"] = "ok"
        except BillingError as exc:
            results["credit"] = exc.error_code
        finally:
            connection.close()

    threads = [
        threading.Thread(target=refund),
        threading.Thread(target=credit_note),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert set(results) == {"refund", "credit"}
    assert "ok" in results.values(), results

    with tenant_context(tenant):
        invoice = Invoice.objects.get(pk=invoice_id)
        refunded = (
            Payment.objects.filter(invoice=invoice, kind=Payment.Kind.REFUND).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        credited = (
            CreditNote.objects.filter(
                invoice=invoice, voided_at__isnull=True
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        net_revenue = invoice.total - Decimal(str(refunded)) - Decimal(str(credited))
        assert net_revenue >= 0
        assert Decimal(str(refunded)) + Decimal(str(credited)) <= invoice.total
        assert CreditNote.objects.filter(invoice=invoice).count() <= 1


@pytest.mark.django_db
def test_idempotency_is_enforced_at_the_database(
    tenant_a: Any, mi_setup: dict[str, Any]
) -> None:
    """The unique index, not just the service check, stops duplicates."""
    with tenant_context(tenant_a):
        invoice = _paid_invoice(mi_setup, "500.00")
        Payment.objects.create(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("10.00"),
            received_by=mi_setup["owner"],
            idempotency_key="mi-db-key-1",
            payload_sha256="hash-1",
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                invoice=invoice,
                kind=Payment.Kind.PAYMENT,
                method=Payment.Method.CASH,
                amount=Decimal("10.00"),
                received_by=mi_setup["owner"],
                idempotency_key="mi-db-key-1",
                payload_sha256="hash-1",
            )

        CreditNote.objects.create(
            number="CN-DB-1",
            invoice=invoice,
            amount=Decimal("10.00"),
            reason="db check",
            method=Payment.Method.CASH,
            reversed_methods={"cash": "10.00"},
            issued_by=mi_setup["owner"],
            idempotency_key="mi-db-cn-1",
            payload_sha256="hash-cn",
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            CreditNote.objects.create(
                number="CN-DB-2",
                invoice=invoice,
                amount=Decimal("10.00"),
                reason="duplicate",
                method=Payment.Method.CASH,
                reversed_methods={"cash": "10.00"},
                issued_by=mi_setup["owner"],
                idempotency_key="mi-db-cn-2",
                payload_sha256="hash-cn-2",
            )


@pytest.mark.django_db
def test_refund_above_net_paid_is_rejected(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        invoice = _paid_invoice(mi_setup, "1000.00")
        invoice_id = invoice.id

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "1000.01",
            "refund_reason": "Too much",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-refund-over-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "refund_exceeds_payments"


@pytest.mark.django_db
def test_owner_keeps_tenant_wide_scope(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Owner is not branch-scoped; a manager/receptionist is."""
    with tenant_context(tenant_a):
        other_branch = BranchFactory(code="MI2", name="Other Lab")
        other_patient = PatientFactory(branch=other_branch)
        invoice = InvoiceFactory(
            patient=other_patient,
            branch=other_branch,
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
        )
        invoice_id = invoice.id

    owner_payment = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "500.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-owner-scope-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert owner_payment.status_code == 201, owner_payment.content

    reception = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "100.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-recep-scope-1",
        headers=auth_headers(mi_setup["receptionist"]),
    )
    assert reception.status_code == 404


@pytest.mark.django_db
def test_money_after_day_close_is_rejected(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """A closed branch-day is final; late cash belongs to the next open day."""
    with tenant_context(tenant_a):
        invoice = _paid_invoice(mi_setup, "500.00")
        invoice_id = invoice.id
        DayClose.objects.create(
            branch=mi_setup["branch"],
            business_date=timezone.localdate(),
            method_totals={},
            total_invoices=1,
            total_discount=Decimal("0.00"),
            total_credit_notes=Decimal("0.00"),
            expected_cash=Decimal("500.00"),
            counted_cash=Decimal("500.00"),
            difference=Decimal("0.00"),
            difference_note=None,
            closed_by=mi_setup["owner"],
        )

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "100.00",
            "refund_reason": "late",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-day-closed-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "day_closed"


@pytest.mark.django_db
def test_balance_is_zero_after_full_credit_note(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """INV-14FACCEF regression:
    total 2,400, paid 2,400, CN 2,400 -> balance 0, status Refunded.
    """
    with tenant_context(tenant_a):
        invoice = _paid_invoice(mi_setup, "2400.00")
        invoice_id = invoice.id

    cn_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={
            "amount": "2400.00",
            "reason": "Customer cancellation INV-14FACCEF",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-full-2400",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_resp.status_code == 201, cn_resp.content

    detail_resp = Client().get(
        f"{INVOICES_URL}/{invoice_id}",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["status"] == "refunded"
    assert data["net_revenue"] == "0.00"
    assert data["balance"] == "0.00"


@pytest.mark.django_db
def test_balance_is_zero_on_cancelled_invoice(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """A cancelled invoice shows balance 0.00."""
    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
        )
        invoice_id = invoice.id

    cancel_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/cancel",
        data={"reason": "Patient requested cancellation"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cancel_resp.status_code == 200, cancel_resp.content

    detail_resp = Client().get(
        f"{INVOICES_URL}/{invoice_id}",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["status"] == "cancelled"
    assert data["balance"] == "0.00"


@pytest.mark.django_db
def test_refund_cannot_exceed_method_net_paid(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Pay 1,000 cash + 1,000 card; two 1,000 refunds both tagged cash
    -> second fails 422 refund_exceeds_method_payments.
    """
    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("2000.00"),
            total=Decimal("2000.00"),
        )
        invoice_id = invoice.id
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
        )
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CARD,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
        )

    # First refund 1,000 cash -> succeeds
    ref1 = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "1000.00",
            "refund_reason": "Refund cash portion",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-meth-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert ref1.status_code == 201, ref1.content

    # Second refund 1,000 cash -> cash has 0 left, card has 1,000
    # -> 422 refund_exceeds_method_payments
    ref2 = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "1000.00",
            "refund_reason": "Attempt second cash refund",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-meth-2",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert ref2.status_code == 422
    assert ref2.json()["error"]["code"] == "refund_exceeds_method_payments"


@pytest.mark.django_db
def test_credit_note_decomposes_across_methods(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Pay 1,000 cash + 1,400 card; CN 2,400 reverses 1,000 cash + 1,400 card."""
    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("2400.00"),
            total=Decimal("2400.00"),
        )
        invoice_id = invoice.id
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
        )
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CARD,
            amount=Decimal("1400.00"),
            received_by=mi_setup["owner"],
        )

    cn_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={
            "amount": "2400.00",
            "reason": "Full reversal decomposing methods",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-decomp-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_resp.status_code == 201, cn_resp.content
    note_data = cn_resp.json()
    assert note_data["reversed_methods"] == {"cash": "1000.00", "card": "1400.00"}


@pytest.mark.django_db
def test_day_close_counts_credit_note_per_method(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Day Close out bucket matches the decomposition above."""
    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("2400.00"),
            total=Decimal("2400.00"),
        )
        invoice_id = invoice.id
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
        )
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CARD,
            amount=Decimal("1400.00"),
            received_by=mi_setup["owner"],
        )

    # Issue CN 2,400
    Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={
            "amount": "2400.00",
            "reason": "Full reversal for day close test",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-dc-1",
        headers=auth_headers(mi_setup["owner"]),
    )

    with tenant_context(tenant_a):
        from apps.billing.services import DayCloseService

        totals = DayCloseService.collect_totals(
            branch_id=mi_setup["branch"].id, day=timezone.localdate()
        )
        method_totals = totals["method_totals"]
        assert method_totals["cash"]["in"] == "1000.00"
        assert method_totals["cash"]["out"] == "1000.00"
        assert method_totals["cash"]["net"] == "0.00"
        assert method_totals["card"]["in"] == "1400.00"
        assert method_totals["card"]["out"] == "1400.00"
        assert method_totals["card"]["net"] == "0.00"
        assert totals["total_credit_notes"] == Decimal("2400.00")


@pytest.mark.django_db
def test_post_close_payment_rolls_to_next_business_day(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Close day D at 21:00; payment at 21:05 -> business_date D+1, 200."""
    from datetime import timedelta

    from apps.billing.services import DayCloseService, get_active_business_date

    today = timezone.localdate()
    with tenant_context(tenant_a):
        # Create an invoice before close
        invoice_d = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        invoice_d_id = invoice_d.id

        # Close day D
        DayCloseService.close(
            actor=mi_setup["owner"],
            branch_id=mi_setup["branch"].id,
            day=today,
            counted_cash=Decimal("0.00"),
            difference_note=None,
        )

        # Verify active business date rolled forward to D+1
        assert get_active_business_date(mi_setup["branch"].id) == (
            today + timedelta(days=1)
        )

    # Post payment arriving after close
    pay_resp = Client().post(
        f"{INVOICES_URL}/{invoice_d_id}/payments",
        data={
            "kind": "payment",
            "method": "cash",
            "amount": "1000.00",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-post-close-pay-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert pay_resp.status_code == 201, pay_resp.content

    with tenant_context(tenant_a):
        payment = Payment.objects.get(invoice_id=invoice_d_id)
        # business_date is D+1, created_at is today
        assert payment.business_date == today + timedelta(days=1)
        assert payment.created_at.date() == today

        # Day D DayClose totals are unchanged (0 in)
        totals_d = DayCloseService.collect_totals(
            branch_id=mi_setup["branch"].id, day=today
        )
        assert totals_d["method_totals"]["cash"]["in"] == "0.00"

        # Day D+1 totals have the 1000.00 payment
        totals_d1 = DayCloseService.collect_totals(
            branch_id=mi_setup["branch"].id, day=today + timedelta(days=1)
        )
        assert totals_d1["method_totals"]["cash"]["in"] == "1000.00"


@pytest.mark.django_db(transaction=True)
def test_inflight_payment_cannot_land_in_closing_day(
    tenant_a: Any, mi_setup: dict[str, Any]
) -> None:
    """Payment and Day Close race: lands or fails 409, never joins closed day."""
    from apps.billing.services import DayCloseService, PaymentService

    tenant = mi_setup["tenant"]
    branch_id = mi_setup["branch"].id
    owner_id = mi_setup["owner"].id
    today = timezone.localdate()

    with tenant_context(tenant):
        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        invoice_id = invoice.id

    payment_outcome: dict[str, Any] = {}
    close_outcome: dict[str, Any] = {}

    def run_payment() -> None:
        try:
            with tenant_context(tenant):
                from apps.accounts.models import StaffUser

                actor = StaffUser.objects.get(pk=owner_id)
                PaymentService.record_payment(
                    invoice_id=invoice_id,
                    kind="payment",
                    method="cash",
                    amount=Decimal("1000.00"),
                    reference=None,
                    idempotency_key="mi-race-pay-1",
                    actor=actor,
                )
                payment_outcome["status"] = "success"
        except BillingError as exc:
            payment_outcome["status"] = exc.error_code
        except Exception as exc:
            payment_outcome["status"] = f"error: {exc}"
        finally:
            connection.close()

    def run_close() -> None:
        try:
            with tenant_context(tenant):
                from apps.accounts.models import StaffUser

                actor = StaffUser.objects.get(pk=owner_id)
                DayCloseService.close(
                    actor=actor,
                    branch_id=branch_id,
                    day=today,
                    counted_cash=Decimal("0.00"),
                    difference_note="race test",
                )
                close_outcome["status"] = "success"
        except BillingError as exc:
            close_outcome["status"] = exc.error_code
        except Exception as exc:
            close_outcome["status"] = f"error: {exc}"
        finally:
            connection.close()

    t1 = threading.Thread(target=run_payment)
    t2 = threading.Thread(target=run_close)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert payment_outcome.get("status") in {"success", "day_closed"}
    assert close_outcome.get("status") in {"success", "already_closed"}

    with tenant_context(tenant):
        day_close = DayClose.objects.filter(
            branch_id=branch_id, business_date=today
        ).first()
        if day_close is not None:
            p = Payment.objects.filter(invoice_id=invoice_id).first()
            if p is not None and p.business_date == today:
                assert Decimal(day_close.method_totals["cash"]["in"]) >= Decimal(
                    "1000.00"
                )


@pytest.mark.django_db
def test_void_after_day_close_adjusts_open_day_not_closed_day(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """CN 2,400 Day 1, close Day 1, void Day 2 -> Day 1 unchanged, Day 2 +2,400."""
    from datetime import timedelta

    from apps.billing.services import DayCloseService, get_active_business_date

    day1 = timezone.localdate()
    day2 = day1 + timedelta(days=1)

    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("2400.00"),
            total=Decimal("2400.00"),
        )
        invoice_id = invoice.id
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
            business_date=day1,
        )
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CARD,
            amount=Decimal("1400.00"),
            received_by=mi_setup["owner"],
            business_date=day1,
        )

    # Issue CN 2,400 on Day 1
    cn_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={
            "amount": "2400.00",
            "reason": "Void test Day 1",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-void-dc-cn-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_resp.status_code == 201
    note_id = cn_resp.json()["id"]

    # Close Day 1
    with tenant_context(tenant_a):
        DayCloseService.close(
            actor=mi_setup["owner"],
            branch_id=mi_setup["branch"].id,
            day=day1,
            counted_cash=Decimal("0.00"),
            difference_note=None,
        )
        totals_day1_pre = DayCloseService.collect_totals(
            branch_id=mi_setup["branch"].id, day=day1
        )
        assert totals_day1_pre["method_totals"]["cash"]["net"] == "0.00"
        assert totals_day1_pre["method_totals"]["card"]["net"] == "0.00"
        assert get_active_business_date(mi_setup["branch"].id) == day2

    # Void CN on Day 2 (current active open day)
    void_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes/{note_id}/void",
        data={"reason": "Reversing erroneous credit note on Day 2"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert void_resp.status_code == 200

    with tenant_context(tenant_a):
        # Day 1 Day Close is completely unchanged
        totals_day1_post = DayCloseService.collect_totals(
            branch_id=mi_setup["branch"].id, day=day1
        )
        assert totals_day1_post["method_totals"]["cash"]["out"] == "1000.00"
        assert totals_day1_post["method_totals"]["card"]["out"] == "1400.00"
        assert totals_day1_post["method_totals"]["cash"]["net"] == "0.00"
        assert totals_day1_post["method_totals"]["card"]["net"] == "0.00"

        # Day 2 Day Close receives the restored amounts into "in" bucket
        totals_day2 = DayCloseService.collect_totals(
            branch_id=mi_setup["branch"].id, day=day2
        )
        assert totals_day2["method_totals"]["cash"]["in"] == "1000.00"
        assert totals_day2["method_totals"]["card"]["in"] == "1400.00"
        assert totals_day2["method_totals"]["cash"]["net"] == "1000.00"
        assert totals_day2["method_totals"]["card"]["net"] == "1400.00"
        assert totals_day2["total_in"] == Decimal("2400.00")

        # Sum of all Day Close net revenues == lifetime invoice net revenue (2400.00)
        net_all_days = totals_day1_post["net_total"] + totals_day2["net_total"]
        assert net_all_days == Decimal("2400.00")


@pytest.mark.django_db
def test_void_is_append_only_event(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Void creates CreditNoteVoid row; CreditNote money fields unchanged."""
    from apps.billing.models import CreditNoteVoid

    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        invoice_id = invoice.id
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
        )

    cn_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={
            "amount": "1000.00",
            "reason": "To be voided",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-void-append-cn-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_resp.status_code == 201
    note_id = cn_resp.json()["id"]

    void_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes/{note_id}/void",
        data={"reason": "Customer mistake corrected"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert void_resp.status_code == 200

    with tenant_context(tenant_a):
        note = CreditNote.objects.get(pk=note_id)
        # Money fields unchanged
        assert note.amount == Decimal("1000.00")
        assert note.method == "cash"

        # CreditNoteVoid row created
        void_event = CreditNoteVoid.objects.get(credit_note=note)
        assert void_event.void_reason == "Customer mistake corrected"
        assert void_event.voided_by == mi_setup["owner"]
        assert void_event.restored_methods == {"cash": "1000.00"}
