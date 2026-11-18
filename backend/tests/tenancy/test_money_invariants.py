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
from apps.accounts.models import Role
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
        patient = PatientFactory(branch=branch)
        return {
            "tenant": tenant_a,
            "branch": branch,
            "owner": owner,
            "receptionist": receptionist,
            "patient": patient,
        }


def _paid_invoice(setup: dict[str, Any], amount: str = "1000.00") -> Invoice:
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
        **auth_headers(mi_setup["owner"]),
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
        **auth_headers(mi_setup["owner"]),
    )
    assert owner_payment.status_code == 201, owner_payment.content

    reception = Client().post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={"kind": "payment", "method": "cash", "amount": "100.00"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="mi-recep-scope-1",
        **auth_headers(mi_setup["receptionist"]),
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
        **auth_headers(mi_setup["owner"]),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "day_closed"
