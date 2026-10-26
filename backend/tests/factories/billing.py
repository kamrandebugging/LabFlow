from decimal import Decimal

import factory

from apps.billing.models import Invoice, InvoiceItem, Payment
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
