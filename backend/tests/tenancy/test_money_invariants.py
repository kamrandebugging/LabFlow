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


@pytest.mark.django_db
def test_manager_daily_cap_counts_credit_notes(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Manager does 5 × 5,000 refunds then a 5,000 credit note -> 429."""
    with tenant_context(tenant_a):
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=mi_setup["branch"], email="mi_mgr_cap@t.com"
        )
        StaffBranch.objects.create(
            staff_user=manager, branch=mi_setup["branch"], is_primary=True
        )

        invoices = []
        for _ in range(5):
            inv = InvoiceFactory(
                patient=mi_setup["patient"],
                branch=mi_setup["branch"],
                status=Invoice.Status.PAID,
                subtotal=Decimal("5000.00"),
                total=Decimal("5000.00"),
            )
            PaymentFactory(
                invoice=inv,
                kind=Payment.Kind.PAYMENT,
                method=Payment.Method.CASH,
                amount=Decimal("5000.00"),
                received_by=manager,
            )
            invoices.append(inv)

        inv6 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00"),
        )
        PaymentFactory(
            invoice=inv6,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("5000.00"),
            received_by=manager,
        )
        inv6_id = inv6.id

    for i, inv in enumerate(invoices):
        r = Client().post(
            f"{INVOICES_URL}/{inv.id}/payments",
            data={
                "kind": "refund",
                "method": "cash",
                "amount": "5000.00",
                "refund_reason": f"Cap test refund {i}",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=f"mi-mgr-ref-{i}",
            headers=auth_headers(manager),
        )
        assert r.status_code == 201, r.content

    cn_resp = Client().post(
        f"{INVOICES_URL}/{inv6_id}/credit-notes",
        data={
            "amount": "5000.00",
            "reason": "Exceeding daily pool",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-mgr-cn-cap-exceeded",
        headers=auth_headers(manager),
    )
    assert cn_resp.status_code == 429, cn_resp.content
    assert cn_resp.json()["code"] == "refund_velocity_exceeded"


@pytest.mark.django_db(transaction=True)
def test_manager_daily_cap_race_across_invoices(
    tenant_a: Any, mi_setup: dict[str, Any]
) -> None:
    """Two concurrent 4k refunds with 18k prior -> one succeeds (total <= 25k)."""
    from apps.billing.services import PaymentService

    tenant = mi_setup["tenant"]
    with tenant_context(tenant):
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=mi_setup["branch"], email="mi_mgr_race@t.com"
        )
        StaffBranch.objects.create(
            staff_user=manager, branch=mi_setup["branch"], is_primary=True
        )
        manager_id = manager.id

        # Prior 18,000 refunded
        inv_prior = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("20000.00"),
            total=Decimal("20000.00"),
        )
        PaymentFactory(
            invoice=inv_prior,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("20000.00"),
            received_by=manager,
        )
        PaymentFactory(
            invoice=inv_prior,
            kind=Payment.Kind.REFUND,
            method=Payment.Method.CASH,
            amount=Decimal("18000.00"),
            received_by=manager,
        )

        # Invoices 1 and 2 for the race
        inv1 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00"),
        )
        PaymentFactory(
            invoice=inv1,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("5000.00"),
            received_by=manager,
        )
        inv1_id = inv1.id

        inv2 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00"),
        )
        PaymentFactory(
            invoice=inv2,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("5000.00"),
            received_by=manager,
        )
        inv2_id = inv2.id

    outcomes: list[str] = []

    def refund_target(inv_id: Any, key: str) -> None:
        try:
            with tenant_context(tenant):
                from apps.accounts.models import StaffUser

                actor = StaffUser.objects.get(pk=manager_id)
                PaymentService.record_payment(
                    invoice_id=inv_id,
                    kind="refund",
                    method="cash",
                    amount=Decimal("4000.00"),
                    reference=None,
                    refund_reason="Race test",
                    idempotency_key=key,
                    actor=actor,
                )
                outcomes.append("success")
        except BillingError as exc:
            outcomes.append(exc.error_code)
        finally:
            connection.close()

    t1 = threading.Thread(target=refund_target, args=(inv1_id, "mi-mgr-race-1"))
    t2 = threading.Thread(target=refund_target, args=(inv2_id, "mi-mgr-race-2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one succeeded and one was blocked by velocity cap
    assert outcomes.count("success") == 1
    assert outcomes.count("refund_velocity_exceeded") == 1

    with tenant_context(tenant):
        from apps.accounts.models import StaffUser
        from apps.billing.services import get_daily_staff_reversal_sum

        actor = StaffUser.objects.get(pk=manager_id)
        total_rev = get_daily_staff_reversal_sum(actor)
        # 18,000 + 4,000 = 22,000 <= 25,000
        assert total_rev == Decimal("22000.00")
        assert total_rev <= Decimal("25000.00")


@pytest.mark.django_db
def test_discount_locked_after_full_refund(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Pay 500, refund 500, then discount edit -> 409 discount_locked.

    net_paid is 0 but a Payment row exists.
    """
    with tenant_context(tenant_a):
        invoice = _paid_invoice(mi_setup, "500.00")
        invoice_id = invoice.id

    # Refund 500
    ref_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "500.00",
            "refund_reason": "Full refund test",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-500-full",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert ref_resp.status_code == 201, ref_resp.content

    # Now attempt discount edit
    patch_resp = Client().patch(
        f"{INVOICES_URL}/{invoice_id}",
        data={"discount_amount": "50.00", "discount_reason": "Belated discount"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert patch_resp.status_code == 409
    assert patch_resp.json()["error"]["code"] == "discount_locked"


@pytest.mark.django_db
def test_zero_total_invoice_can_be_cancelled(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """100% discount, total 0, no samples -> Cancelled.

    With a collected sample -> 409.
    """
    with tenant_context(tenant_a):
        inv1 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("500.00"),
            discount_amount=Decimal("500.00"),
            discount_reason="100% courtesy discount",
            total=Decimal("0.00"),
        )
        inv1_id = inv1.id

    cancel1 = Client().post(
        f"{INVOICES_URL}/{inv1_id}/cancel",
        data={"reason": "Patient decided not to test"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cancel1.status_code == 200, cancel1.content
    assert cancel1.json()["status"] == "cancelled"

    # With a collected sample:
    with tenant_context(tenant_a):
        from tests.factories.samples import SampleFactory

        inv2 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("500.00"),
            discount_amount=Decimal("500.00"),
            discount_reason="100% courtesy discount",
            total=Decimal("0.00"),
        )
        SampleFactory(invoice=inv2, branch=mi_setup["branch"])
        inv2_id = inv2.id

    cancel2 = Client().post(
        f"{INVOICES_URL}/{inv2_id}/cancel",
        data={"reason": "Try cancelling after sample"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cancel2.status_code == 409
    assert cancel2.json()["error"]["code"] == "invalid_state_transition"


@pytest.mark.django_db
def test_cash_refund_needs_no_reference(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Cash refund with reason, no reference -> 201.

    Card refund without reference -> 422.
    """
    with tenant_context(tenant_a):
        inv = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("2000.00"),
            total=Decimal("2000.00"),
        )
        PaymentFactory(
            invoice=inv,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
        )
        PaymentFactory(
            invoice=inv,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CARD,
            amount=Decimal("1000.00"),
            reference="TXN-CARD-999",
            received_by=mi_setup["owner"],
        )
        inv_id = inv.id

    # Cash refund without reference -> 201
    cash_ref = Client().post(
        f"{INVOICES_URL}/{inv_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "500.00",
            "refund_reason": "Cash refund reason",
            "reference": None,
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cash-ref-no-ref",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cash_ref.status_code == 201, cash_ref.content

    # Card refund without reference -> 422 reference_required
    card_ref = Client().post(
        f"{INVOICES_URL}/{inv_id}/payments",
        data={
            "kind": "refund",
            "method": "card",
            "amount": "500.00",
            "refund_reason": "Card refund reason",
            "reference": None,
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-card-ref-no-ref",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert card_ref.status_code == 422
    assert card_ref.json()["error"]["code"] == "reference_required"


@pytest.mark.django_db
def test_referral_discount_requires_active_partner_id(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Inactive partner -> 422 inactive_referral_partner;
    reason without partner_id -> 422 referral_partner_required;
    partner name typed in reason but partner_id null -> 422 referral_partner_required.
    """
    with tenant_context(tenant_a):
        from tests.factories.catalog import TestFactory
        from tests.factories.partners import ReferralPartnerFactory

        test = TestFactory(price=Decimal("1000.00"))
        inactive_partner = ReferralPartnerFactory(is_active=False, name="Dr. Inactive")
        ReferralPartnerFactory(is_active=True, name="Dr. Active")
        patient = mi_setup["patient"]
        branch = mi_setup["branch"]
        test_id = str(test.id)
        inact_id = str(inactive_partner.id)

    # Inactive partner -> 422 inactive_referral_partner
    resp1 = Client().post(
        f"{INVOICES_URL}",
        data={
            "patient_id": str(patient.id),
            "branch_id": str(branch.id),
            "items": [{"test_id": test_id, "quantity": 1}],
            "referral_partner_id": inact_id,
            "discount_amount": "100.00",
            "discount_reason": "Referral discount",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-inact-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert resp1.status_code == 422
    assert resp1.json()["error"]["code"] == "inactive_referral_partner"

    # Reason with 'referral' but partner_id null -> 422 referral_partner_required
    resp2 = Client().post(
        f"{INVOICES_URL}",
        data={
            "patient_id": str(patient.id),
            "branch_id": str(branch.id),
            "items": [{"test_id": test_id, "quantity": 1}],
            "referral_partner_id": None,
            "discount_amount": "100.00",
            "discount_reason": "Referral discount from hospital",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-null-partner-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "referral_partner_required"

    # Partner name typed in reason but partner_id null -> 422 referral_partner_required
    resp3 = Client().post(
        f"{INVOICES_URL}",
        data={
            "patient_id": str(patient.id),
            "branch_id": str(branch.id),
            "items": [{"test_id": test_id, "quantity": 1}],
            "referral_partner_id": None,
            "discount_amount": "100.00",
            "discount_reason": "Dr. Active",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-partner-name-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert resp3.status_code == 422
    assert resp3.json()["error"]["code"] == "referral_partner_required"


@pytest.mark.django_db
def test_invoice_referral_snapshot_immutable(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Change patient.referral_partner after invoice creation.

    Invoice referral_partner_id unchanged; discount edit on that invoice -> 409.
    """
    with tenant_context(tenant_a):
        from tests.factories.partners import ReferralPartnerFactory

        partner1 = ReferralPartnerFactory(is_active=True, name="Partner One")
        partner2 = ReferralPartnerFactory(is_active=True, name="Partner Two")
        patient = mi_setup["patient"]
        patient.referral_partner = partner1
        patient.save()

        invoice = InvoiceFactory(
            patient=patient,
            branch=mi_setup["branch"],
            referral_partner=partner1,
            status=Invoice.Status.PAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("1000.00"),
            received_by=mi_setup["owner"],
        )
        invoice_id = invoice.id
        p2_id = partner2.id

    # Change patient referral partner
    with tenant_context(tenant_a):
        patient.referral_partner = partner2
        patient.save()
        invoice.refresh_from_db()
        assert invoice.referral_partner_id == partner1.id

    # Try to edit referral partner on invoice with existing payment -> 409
    patch_resp = Client().patch(
        f"{INVOICES_URL}/{invoice_id}",
        data={"referral_partner_id": str(p2_id)},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert patch_resp.status_code == 409
    assert patch_resp.json()["error"]["code"] == "invalid_state_transition"


@pytest.mark.django_db
def test_line_cancel_removes_unperformed_test(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Pay 2,400 for two tests, cancel the unperformed 1,600 line, refund 1,600
    -> net_revenue 800, balance 0, status Paid.
    """
    with tenant_context(tenant_a):
        from tests.factories.billing import InvoiceItemFactory
        from tests.factories.catalog import TestFactory

        test1 = TestFactory(name="Sputum for AFB", price=Decimal("1600.00"))
        test2 = TestFactory(name="CBC", price=Decimal("800.00"))

        invoice = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.PAID,
            subtotal=Decimal("2400.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("2400.00"),
        )
        item1 = InvoiceItemFactory(
            invoice=invoice,
            test=test1,
            unit_price=Decimal("1600.00"),
            quantity=1,
            line_total=Decimal("1600.00"),
        )
        InvoiceItemFactory(
            invoice=invoice,
            test=test2,
            unit_price=Decimal("800.00"),
            quantity=1,
            line_total=Decimal("800.00"),
        )
        PaymentFactory(
            invoice=invoice,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("2400.00"),
            received_by=mi_setup["owner"],
        )
        invoice_id = invoice.id
        item1_id = item1.id

    # Cancel unperformed line 1 (1,600.00)
    cancel_line_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/lines/{item1_id}/cancel",
        data={"reason": "Patient refused Sputum test"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cancel_line_resp.status_code == 200, cancel_line_resp.content

    # Refund 1,600.00
    ref_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "1600.00",
            "refund_reason": "Refund for cancelled Sputum line",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-line-cancel-1600",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert ref_resp.status_code == 201, ref_resp.content

    # Check invoice detail: net_revenue 800, balance 0, status Paid
    detail_resp = Client().get(
        f"{INVOICES_URL}/{invoice_id}",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["total"] == "800.00"
    assert detail["net_revenue"] == "800.00"
    assert detail["balance"] == "0.00"
    assert detail["status"] == "paid"


@pytest.mark.django_db
def test_fully_refunded_invoice_can_be_closed_after_void(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """CN issued, voided, full refund 2,400.

    Owner closes it to Cancelled, balance 0.
    """
    with tenant_context(tenant_a):
        invoice = _paid_invoice(mi_setup, "2400.00")
        invoice_id = invoice.id

    # 1. Issue credit note 2,400
    cn_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={
            "amount": "2400.00",
            "reason": "Mistaken billing",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-close-2400",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_resp.status_code == 201, cn_resp.content
    note_id = cn_resp.json()["id"]

    # 2. Void the credit note
    void_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes/{note_id}/void",
        data={"reason": "Voiding credit note to allow proper refund"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert void_resp.status_code == 200, void_resp.content

    # Sample drawn afterwards (proving terminal closure works even if a sample exists)
    with tenant_context(tenant_a):
        from tests.factories.samples import SampleFactory

        SampleFactory(invoice=invoice, branch=mi_setup["branch"])

    # 3. Full refund 2,400
    ref_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "refund",
            "method": "cash",
            "amount": "2400.00",
            "refund_reason": "Full refund after void",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-ref-after-void-2400",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert ref_resp.status_code == 201, ref_resp.content

    # 4. Owner closes it to Cancelled
    close_resp = Client().post(
        f"{INVOICES_URL}/{invoice_id}/cancel",
        data={"reason": "Terminal closure after void and full refund"},
        content_type="application/json",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert close_resp.status_code == 200, close_resp.content
    assert close_resp.json()["status"] == "cancelled"

    detail_resp = Client().get(
        f"{INVOICES_URL}/{invoice_id}",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "cancelled"
    assert detail["balance"] == "0.00"
    assert detail["net_revenue"] == "0.00"


@pytest.mark.django_db
def test_credit_note_blocked_when_sample_collected(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Sample collected -> CN 409 sample_already_collected.

    Clinically cancelled sample -> CN succeeds.
    No sample -> CN succeeds.
    """
    from tests.factories.samples import SampleFactory

    # 1. Invoice with collected sample -> 409 sample_already_collected
    with tenant_context(tenant_a):
        inv1 = _paid_invoice(mi_setup, "1000.00")
        sample1 = SampleFactory(invoice=inv1, branch=mi_setup["branch"])
        inv1_id = inv1.id
        sample1_id = sample1.id

    cn_fail = Client().post(
        f"{INVOICES_URL}/{inv1_id}/credit-notes",
        data={
            "amount": "1000.00",
            "reason": "Test CN with collected sample",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-sample-collected-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_fail.status_code == 409, cn_fail.content
    assert cn_fail.json()["error"]["code"] == "sample_already_collected"

    # 2. Clinically cancel the sample -> credit note succeeds
    with tenant_context(tenant_a):
        from apps.samples.services import SampleService

        SampleService.cancel_sample(
            sample_id=sample1_id,
            reason="Sample hemolyzed and cancelled clinically",
            actor=mi_setup["owner"],
        )

    cn_ok = Client().post(
        f"{INVOICES_URL}/{inv1_id}/credit-notes",
        data={
            "amount": "1000.00",
            "reason": "Test CN after sample cancelled clinically",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-sample-cancelled-ok",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_ok.status_code == 201, cn_ok.content

    # 3. Invoice with NO sample -> credit note succeeds as today
    with tenant_context(tenant_a):
        inv2 = _paid_invoice(mi_setup, "1500.00")
        inv2_id = inv2.id

    cn_no_sample = Client().post(
        f"{INVOICES_URL}/{inv2_id}/credit-notes",
        data={
            "amount": "1500.00",
            "reason": "Test CN with no samples",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-no-sample-ok",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_no_sample.status_code == 201, cn_no_sample.content


@pytest.mark.django_db
def test_credit_note_blocked_when_report_approved(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Approved report or approved result -> CN 409 report_already_approved."""
    from apps.results.models import Result
    from tests.factories.catalog import TestFactory
    from tests.factories.results import ResultFactory
    from tests.factories.samples import SampleFactory

    with tenant_context(tenant_a):
        inv = _paid_invoice(mi_setup, "2000.00")
        sample = SampleFactory(invoice=inv, branch=mi_setup["branch"])
        test = TestFactory(price=Decimal("2000.00"))
        ResultFactory(
            sample=sample,
            test=test,
            status=Result.Status.APPROVED,
        )
        inv_id = inv.id

    cn_resp = Client().post(
        f"{INVOICES_URL}/{inv_id}/credit-notes",
        data={
            "amount": "2000.00",
            "reason": "Test CN with approved report",
            "method": "cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-cn-report-approved-1",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert cn_resp.status_code == 409, cn_resp.content
    assert cn_resp.json()["error"]["code"] == "report_already_approved"


@pytest.mark.django_db(transaction=True)
def test_sample_collect_and_cancel_race(
    tenant_a: Any, mi_setup: dict[str, Any]
) -> None:
    """Cancel and Collect fired together:

    Invoice ends Cancelled with NO collected sample, or collected with cancel rejected —
    never Cancelled WITH a collected sample.
    """
    from apps.accounts.models import StaffUser
    from apps.billing.services import InvoiceQueryService
    from apps.samples.models import Sample
    from apps.samples.services import SampleService
    from tests.factories.billing import InvoiceItemFactory
    from tests.factories.catalog import TestFactory

    tenant = mi_setup["tenant"]
    with tenant_context(tenant):
        test = TestFactory(price=Decimal("1000.00"))
        inv = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        InvoiceItemFactory(
            invoice=inv,
            test=test,
            unit_price=Decimal("1000.00"),
            quantity=1,
            line_total=Decimal("1000.00"),
        )
        invoice_id = inv.id
        owner_id = mi_setup["owner"].id

    outcomes: dict[str, str] = {}

    def do_collect() -> None:
        try:
            with tenant_context(tenant):
                actor = StaffUser.objects.get(pk=owner_id)
                SampleService.collect_sample(
                    invoice_id=invoice_id,
                    invoice_item_ids=None,
                    actor=actor,
                )
                outcomes["collect"] = "collected"
        except Exception as exc:
            outcomes["collect"] = getattr(exc, "error_code", type(exc).__name__)
        finally:
            connection.close()

    def do_cancel() -> None:
        try:
            with tenant_context(tenant):
                actor = StaffUser.objects.get(pk=owner_id)
                InvoiceQueryService.cancel_invoice(
                    invoice_id=invoice_id,
                    reason="Raced cancellation",
                    actor=actor,
                )
                outcomes["cancel"] = "cancelled"
        except Exception as exc:
            outcomes["cancel"] = getattr(exc, "error_code", type(exc).__name__)
        finally:
            connection.close()

    t1 = threading.Thread(target=do_collect)
    t2 = threading.Thread(target=do_cancel)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    with tenant_context(tenant):
        inv.refresh_from_db()
        collected_samples = list(
            Sample.objects.filter(invoice=inv).exclude(status=Sample.Status.CANCELLED)
        )
        if inv.status == Invoice.Status.CANCELLED:
            assert len(collected_samples) == 0
            assert outcomes["cancel"] == "cancelled"
            assert outcomes["collect"] in ("invoice_cancelled", "InvoiceCancelledError")
        else:
            assert len(collected_samples) > 0
            assert outcomes["collect"] == "collected"
            assert outcomes["cancel"] == "invalid_state_transition"


@pytest.mark.django_db
def test_patient_search_is_tenant_wide_invoices_are_branch_scoped(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Patient search is tenant-wide across branches; invoices are branch-scoped."""
    with tenant_context(tenant_a):
        br1 = mi_setup["branch"]
        br2 = BranchFactory(code="BR2", name="Branch Two")
        recep_br2 = StaffUserFactory(
            role=Role.RECEPTION, branch=br2, email="recep_br2@t.com"
        )
        StaffBranch.objects.create(staff_user=recep_br2, branch=br2, is_primary=True)

        # Patient registered at br1
        pat = PatientFactory(branch=br1, phone="+923001234567", name="Tenant Patient")
        inv_br1 = InvoiceFactory(
            patient=pat,
            branch=br1,
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
        )
        inv_br1_id = inv_br1.id

    # Recep from br2 searches for patient by phone -> 200 and finds patient
    search_resp = Client().get(
        "/api/v1/patients",
        {"q": pat.phone},
        headers=auth_headers(recep_br2),
    )
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert any(p["id"] == str(pat.id) for p in results)

    # Recep from br2 tries to GET br1's invoice -> 404 (strictly branch scoped)
    inv_resp = Client().get(
        f"{INVOICES_URL}/{inv_br1_id}",
        headers=auth_headers(recep_br2),
    )
    assert inv_resp.status_code == 404


@pytest.mark.django_db
def test_pathologist_cross_branch_read_only(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Pathologist GET on another branch's invoice -> 200; POST payment -> 403."""
    with tenant_context(tenant_a):
        br1 = mi_setup["branch"]
        br2 = BranchFactory(code="BR2", name="Branch Two")
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=br2, email="patho@t.com"
        )
        StaffBranch.objects.create(staff_user=pathologist, branch=br2, is_primary=True)

        inv_br1 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=br1,
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
        )
        inv_id = inv_br1.id

    # Pathologist GET on br1's invoice -> 200 (clinical context read)
    get_resp = Client().get(
        f"{INVOICES_URL}/{inv_id}",
        headers=auth_headers(pathologist),
    )
    assert get_resp.status_code == 200

    # Pathologist POST payment on invoice -> 403 (forbidden for billing writes)
    post_resp = Client().post(
        f"{INVOICES_URL}/{inv_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "500.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-patho-pay-1",
        headers=auth_headers(pathologist),
    )
    assert post_resp.status_code == 403


@pytest.mark.django_db
def test_disabled_role_rejected_mid_session(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Platform disables Manager while session live -> next request 403."""
    with tenant_context(tenant_a):
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=mi_setup["branch"], email="mgr_live@t.com"
        )
        StaffBranch.objects.create(
            staff_user=manager, branch=mi_setup["branch"], is_primary=True
        )
        tenant_a.enabled_roles = ["owner", "manager", "reception"]
        tenant_a.save()

    # Manager makes a valid request -> 200
    r1 = Client().get(
        f"{INVOICES_URL}",
        headers=auth_headers(manager),
    )
    assert r1.status_code == 200

    # Platform disables Manager
    with tenant_context(tenant_a):
        tenant_a.enabled_roles = ["owner", "reception"]
        tenant_a.save()

    # Manager's very next request with same session token -> 403
    r2 = Client().get(
        f"{INVOICES_URL}",
        headers=auth_headers(manager),
    )
    assert r2.status_code == 403


@pytest.mark.django_db
def test_soft_delete_blocked_with_open_invoice(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Patient with Partial invoice -> soft-delete 409 open_invoices_exist."""
    with tenant_context(tenant_a):
        patient = PatientFactory(branch=mi_setup["branch"])
        inv = InvoiceFactory(
            patient=patient,
            branch=mi_setup["branch"],
            status=Invoice.Status.PARTIAL,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        PaymentFactory(
            invoice=inv,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("400.00"),
            received_by=mi_setup["owner"],
        )
        pat_id = patient.id

    del_resp = Client().delete(
        f"/api/v1/patients/{pat_id}",
        headers=auth_headers(mi_setup["owner"]),
    )
    assert del_resp.status_code == 409
    assert del_resp.json()["error"]["code"] == "open_invoices_exist"


@pytest.mark.django_db
def test_idempotency_scoped_per_invoice(
    tenant_a: Any, mi_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Same key on two different invoices -> both succeed;
    same key + changed amount on same invoice -> 409.
    """
    with tenant_context(tenant_a):
        inv1 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        inv2 = InvoiceFactory(
            patient=mi_setup["patient"],
            branch=mi_setup["branch"],
            status=Invoice.Status.UNPAID,
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
        )
        inv1_id = inv1.id
        inv2_id = inv2.id

    shared_key = "mi-scoped-idem-key-123"

    # Payment on inv1 with shared_key -> 201
    p1 = Client().post(
        f"{INVOICES_URL}/{inv1_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "500.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=shared_key,
        headers=auth_headers(mi_setup["owner"]),
    )
    assert p1.status_code == 201, p1.content

    # Payment on inv2 with SAME shared_key -> 201 (scoped per invoice!)
    p2 = Client().post(
        f"{INVOICES_URL}/{inv2_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "500.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=shared_key,
        headers=auth_headers(mi_setup["owner"]),
    )
    assert p2.status_code == 201, p2.content

    # Payment on inv1 with same shared_key but CHANGED amount -> 409
    p3 = Client().post(
        f"{INVOICES_URL}/{inv1_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "300.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=shared_key,
        headers=auth_headers(mi_setup["owner"]),
    )
    assert p3.status_code == 409
    assert p3.json()["error"]["code"] == "idempotency_key_reused"
