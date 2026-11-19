from datetime import date
from decimal import Decimal

import factory

from apps.billing.models import (
    BranchDay,
    CreditNote,
    CreditNoteSequence,
    CreditNoteVoid,
    DayClose,
    Invoice,
    InvoiceItem,
    InvoiceLineCancelled,
    Payment,
)
from tests.factories.accounts import StaffUserFactory
from tests.factories.base import TenantModelFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.patients import PatientFactory


class InvoiceFactory(TenantModelFactory):
    class Meta:
        model = Invoice

    patient = factory.SubFactory(PatientFactory)
    branch = factory.SubFactory(BranchFactory)
    referral_partner = None
    status = Invoice.Status.UNPAID
    subtotal = Decimal("1500.00")
    discount_amount = Decimal("0.00")
    discount_reason = None
    total = Decimal("1500.00")
    idempotency_key = factory.Sequence(lambda n: f"inv-idem-key-{n + 1:06d}")


class InvoiceItemFactory(TenantModelFactory):
    class Meta:
        model = InvoiceItem

    invoice = factory.SubFactory(InvoiceFactory)
    test = factory.SubFactory(TestFactory)
    panel = None
    description = factory.LazyAttribute(
        lambda o: o.test.name if o.test else "Billed Item"
    )
    unit_price = Decimal("1500.00")
    quantity = 1
    line_total = Decimal("1500.00")


class PaymentFactory(TenantModelFactory):
    class Meta:
        model = Payment

    invoice = factory.SubFactory(InvoiceFactory)
    kind = Payment.Kind.PAYMENT
    method = Payment.Method.CASH
    amount = Decimal("1500.00")
    received_by = factory.SubFactory(StaffUserFactory)
    reference = None
    idempotency_key = factory.Sequence(lambda n: f"pay-idem-key-{n + 1:06d}")


class CreditNoteSequenceFactory(TenantModelFactory):
    class Meta:
        model = CreditNoteSequence

    id = 1
    last_number = 0


class CreditNoteFactory(TenantModelFactory):
    class Meta:
        model = CreditNote

    number = factory.Sequence(lambda n: f"CN-{n + 1:06d}")
    invoice = factory.SubFactory(InvoiceFactory)
    amount = Decimal("1500.00")
    reason = "Test credit note"
    method = Payment.Method.CASH
    reversed_methods = factory.LazyAttribute(lambda o: {"cash": "1500.00"})
    issued_by = factory.SubFactory(StaffUserFactory)


class DayCloseFactory(TenantModelFactory):
    class Meta:
        model = DayClose

    branch = factory.SubFactory(BranchFactory)
    business_date = factory.Sequence(lambda n: date(2026, 1, (n % 28) + 1))
    method_totals = factory.LazyFunction(dict)
    total_invoices = 1
    total_discount = Decimal("0.00")
    total_credit_notes = Decimal("0.00")
    expected_cash = Decimal("0.00")
    counted_cash = Decimal("0.00")
    difference = Decimal("0.00")
    difference_note = None
    closed_by = factory.SubFactory(StaffUserFactory)


class BranchDayFactory(TenantModelFactory):
    class Meta:
        model = BranchDay

    branch = factory.SubFactory(BranchFactory)
    business_date = factory.Sequence(lambda n: date(2026, 1, (n % 28) + 1))
    is_closed = False


class CreditNoteVoidFactory(TenantModelFactory):
    class Meta:
        model = CreditNoteVoid

    credit_note = factory.SubFactory(CreditNoteFactory)
    voided_by = factory.SubFactory(StaffUserFactory)
    void_reason = "Test void"
    void_business_date = factory.Sequence(lambda n: date(2026, 1, (n % 28) + 1))
    restored_methods = factory.LazyAttribute(lambda o: {"cash": "1500.00"})


class InvoiceLineCancelledFactory(TenantModelFactory):
    class Meta:
        model = InvoiceLineCancelled

    invoice = factory.SubFactory(InvoiceFactory)
    item = factory.SubFactory(
        InvoiceItemFactory,
        invoice=factory.SelfAttribute("..invoice"),
    )
    cancelled_by = factory.SubFactory(StaffUserFactory)
    reason = "Test line cancellation"
    amount_removed = Decimal("500.00")
