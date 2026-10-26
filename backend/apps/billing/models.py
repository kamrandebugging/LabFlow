import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.db.models.functions import Now


class Invoice(models.Model):
    """A bill for one patient at one branch (Doc 02 §5.4).

    Status is CHECK-constrained at the database level.
    idempotency_key carries a partial UNIQUE index WHERE idempotency_key IS NOT NULL.
    """

    class Status(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="invoices",
        db_column="patient_id",
        db_index=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="invoices",
        db_column="branch_id",
        db_index=False,
    )
    referral_partner = models.ForeignKey(
        "partners.ReferralPartner",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
        db_column="referral_partner_id",
        db_index=False,
    )
    status = models.TextField(
        choices=Status.choices,
        default=Status.UNPAID,
        db_default=Status.UNPAID,
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        db_default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        db_default=Decimal("0.00"),
    )
    discount_reason = models.TextField(null=True, blank=True)  # noqa: DJ001
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        db_default=Decimal("0.00"),
    )
    idempotency_key = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "invoice"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "unpaid",
                        "partial",
                        "paid",
                        "refunded",
                        "cancelled",
                    ]
                ),
                name="chk_invoice_status",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=Decimal("0.00")),
                name="chk_invoice_subtotal_non_neg",
            ),
            models.CheckConstraint(
                condition=Q(discount_amount__gte=Decimal("0.00")),
                name="chk_invoice_discount_amount_non_neg",
            ),
            models.CheckConstraint(
                condition=Q(total__gte=Decimal("0.00")),
                name="chk_invoice_total_non_neg",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uq_invoice_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(
                fields=["patient"],
                name="idx_invoice_patient_id",
            ),
            models.Index(
                fields=["branch"],
                name="idx_invoice_branch_id",
            ),
            models.Index(
                fields=["referral_partner"],
                name="idx_invoice_referral_partner_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Invoice({self.id}) [{self.status}] PKR {self.total}"


class InvoiceItem(models.Model):
    """One billed line on an invoice: a test XOR a panel at the snapshot price charged
    (Doc 02 §5.4).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="items",
        db_column="invoice_id",
        db_index=False,
    )
    test = models.ForeignKey(
        "catalog.Test",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_items",
        db_column="test_id",
        db_index=False,
    )
    panel = models.ForeignKey(
        "catalog.Panel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_items",
        db_column="panel_id",
        db_index=False,
    )
    description = models.TextField()
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    quantity = models.IntegerField(
        default=1,
        db_default=1,
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "invoice_item"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(test__isnull=False, panel__isnull=True)
                    | Q(test__isnull=True, panel__isnull=False)
                ),
                name="chk_invoice_item_test_xor_panel",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=Decimal("0.00")),
                name="chk_invoice_item_unit_price_non_neg",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="chk_invoice_item_quantity_pos",
            ),
            models.CheckConstraint(
                condition=Q(line_total__gte=Decimal("0.00")),
                name="chk_invoice_item_line_total_non_neg",
            ),
        ]
        indexes = [
            models.Index(
                fields=["invoice"],
                name="idx_invoice_item_invoice_id",
            ),
            models.Index(
                fields=["test"],
                name="idx_invoice_item_test_id",
            ),
            models.Index(
                fields=["panel"],
                name="idx_invoice_item_panel_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.description} x{self.quantity} = PKR {self.line_total}"
