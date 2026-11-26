import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.db.models.functions import Now
from django.utils import timezone

from apps.branches.scoping import BranchScopedManager


class Invoice(models.Model):
    """A bill for one patient at one branch (Doc 02 §5.4).

    Status is CHECK-constrained at the database level.
    idempotency_key carries a partial UNIQUE index WHERE idempotency_key IS NOT NULL.

    Branch scope (Doc 04 §8.5): ``branch_scope_field = "branch_id"``.
    """

    class Status(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"
        VOIDED = "voided", "Voided"

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
    payload_sha256 = models.TextField(null=True, blank=True)  # noqa: DJ001
    pickup_code_hash = models.TextField(null=True, blank=True)  # noqa: DJ001
    pickup_code_expires_at = models.DateTimeField(null=True, blank=True)
    business_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )
    pickup_access_code: str | None = None

    branch_scope_field = "branch_id"
    objects = BranchScopedManager()

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
                        "voided",
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
    is_cancelled = models.BooleanField(
        default=False,
        db_default=False,
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


class Payment(models.Model):
    """Money received against an invoice — or returned (Doc 02 §5.4, §12).

    Append-only financial fact: created_at only, never updated_at or deleted_at.
    kind and method are separate CHECK-constrained columns; amount is always > 0.
    """

    class Kind(models.TextChoices):
        PAYMENT = "payment", "Payment"
        REFUND = "refund", "Refund"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        EASYPAISA = "easypaisa", "Easypaisa"
        JAZZCASH = "jazzcash", "JazzCash"
        OTHER = "other", "Other"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="payments",
        db_column="invoice_id",
        db_index=False,
    )
    kind = models.TextField(
        choices=Kind.choices,
        default=Kind.PAYMENT,
        db_default=Kind.PAYMENT,
    )
    method = models.TextField(
        choices=Method.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    received_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="received_payments",
        db_column="received_by",
        db_index=False,
    )
    reference = models.TextField(null=True, blank=True)  # noqa: DJ001
    refund_reason = models.TextField(null=True, blank=True)  # noqa: DJ001
    idempotency_key = models.TextField(null=True, blank=True)  # noqa: DJ001
    payload_sha256 = models.TextField(null=True, blank=True)  # noqa: DJ001
    business_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "payment"
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["payment", "refund"]),
                name="chk_payment_kind",
            ),
            models.CheckConstraint(
                condition=Q(
                    method__in=[
                        "cash",
                        "card",
                        "bank_transfer",
                        "easypaisa",
                        "jazzcash",
                        "other",
                    ]
                ),
                name="chk_payment_method",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=Decimal("0.00")),
                name="chk_payment_amount_pos",
            ),
            models.UniqueConstraint(
                fields=["invoice", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uq_payment_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(
                fields=["invoice"],
                name="idx_payment_invoice_id",
            ),
            models.Index(
                fields=["received_by"],
                name="idx_payment_received_by",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment({self.id}) [{self.kind}/{self.method}] PKR {self.amount}"


class CreditNoteSequence(models.Model):
    """Single-row counter that hands out sequential credit-note numbers.

    Numbers are allocated under ``SELECT ... FOR UPDATE`` inside the same
    transaction as the insert, so concurrent issues can never collide and the
    sequence stays gapless in issue order.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "billing_credit_note_sequence"

    def __str__(self) -> str:
        return f"CreditNoteSequence(last={self.last_number})"


class CreditNote(models.Model):
    """Reversing credit note against a paid or partially paid invoice.

    Append-only by design: the API exposes issue + read only, there is no
    update or delete path, and the original invoice row is never modified —
    this document *is* the reversal record.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    number = models.TextField(unique=True)
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="credit_notes",
        db_column="invoice_id",
        db_index=False,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    # Which payment method(s) this reversal returns money from. Stored as
    # {method: "0.00"} so day close can reconcile the cash drawer.
    method = models.TextField(
        choices=Payment.Method.choices,
        default=Payment.Method.CASH,
        db_default=Payment.Method.CASH,
    )
    reversed_methods = models.JSONField(default=dict)
    issued_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="credit_notes_issued",
        db_column="issued_by_id",
        db_index=False,
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    business_date = models.DateField(default=timezone.localdate)
    idempotency_key = models.TextField(null=True, blank=True)  # noqa: DJ001
    payload_sha256 = models.TextField(null=True, blank=True)  # noqa: DJ001
    # Void is an append-only correction: the row and its CN number stay, the
    # voided document stops counting toward revenue, and the event is audited.
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credit_notes_voided",
        db_column="voided_by_id",
        db_index=False,
    )
    void_reason = models.TextField(null=True, blank=True)  # noqa: DJ001

    class Meta:
        db_table = "billing_credit_note"
        ordering = ["issued_at", "number"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="chk_credit_note_amount_pos",
            ),
            # Exactly one credit note per invoice, ever — voiding keeps the
            # row, so it can never be replaced by a second note.
            models.UniqueConstraint(
                fields=["invoice"],
                name="uq_credit_note_invoice",
            ),
            models.UniqueConstraint(
                fields=["invoice", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uq_credit_note_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["invoice"], name="idx_credit_note_invoice_id"),
        ]

    def __str__(self) -> str:
        return f"CreditNote({self.number}) PKR {self.amount}"


class DayClose(models.Model):
    """One branch's reconciled, locked business day (append-only).

    Day Close per-method "out" totals are built from BOTH Payment(kind='refund')
    rows AND non-voided CreditNote per-method reversals for that branch-day.
    Day Close also reports total invoices, total discount given, and total credit
    notes issued — these live on Invoice/CreditNote, not Payment; the aggregation
    rule must name all three sources.

    ``method_totals`` is ``{method: {"in": "0.00", "out": "0.00",
    "net": "0.00"}}`` — the same six payment methods, Decimal PKR rendered as
    strings so the stored document is exact.

    Branch scope (Doc 04 §8.5): ``branch_scope_field = "branch_id"``.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="day_closes",
        db_column="branch_id",
        db_index=False,
    )
    business_date = models.DateField()
    method_totals = models.JSONField()
    counted_methods = models.JSONField(default=dict)
    method_differences = models.JSONField(default=dict)
    total_invoices = models.PositiveIntegerField(default=0)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_credit_notes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2)
    difference = models.DecimalField(max_digits=12, decimal_places=2)
    difference_note = models.TextField(null=True, blank=True)  # noqa: DJ001
    closed_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="day_closes",
        db_column="closed_by",
        db_index=False,
    )
    approved_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_day_closes",
        db_column="approved_by",
        db_index=False,
    )
    closed_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    superseded_at = models.DateTimeField(null=True, blank=True)

    branch_scope_field = "branch_id"
    objects = BranchScopedManager()

    class Meta:
        db_table = "billing_day_close"
        ordering = ["-business_date", "-closed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "business_date"],
                condition=Q(superseded_at__isnull=True),
                name="uq_day_close_active_branch_date",
            ),
        ]
        indexes = [
            models.Index(fields=["branch"], name="idx_day_close_branch_id"),
        ]

    def __str__(self) -> str:
        return f"DayClose({self.branch_id} {self.business_date})"


class DayCloseReopen(models.Model):
    """Append-only reopen/correction event for a closed branch-day."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    day_close = models.OneToOneField(
        "billing.DayClose",
        on_delete=models.PROTECT,
        related_name="reopen_event",
        db_column="day_close_id",
        db_index=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="day_close_reopens",
        db_column="branch_id",
        db_index=False,
    )
    business_date = models.DateField()
    reopened_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="day_close_reopens",
        db_column="reopened_by",
        db_index=False,
    )
    reopened_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()

    class Meta:
        db_table = "billing_day_close_reopen"
        ordering = ["-reopened_at"]
        indexes = [
            models.Index(
                fields=["branch", "business_date"],
                name="idx_day_close_reopen_br_date",
            ),
        ]

    def __str__(self) -> str:
        return f"DayCloseReopen({self.branch_id} {self.business_date})"


class BranchDay(models.Model):
    """Business-day control record for each branch (Phase 3 Rule 1 & 3)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="branch_days",
        db_column="branch_id",
        db_index=False,
    )
    business_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_branch_day"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "business_date"],
                name="uq_branch_day_branch_date",
            ),
        ]
        indexes = [
            models.Index(
                fields=["branch", "business_date"],
                name="idx_branch_day_branch_date",
            ),
        ]

    def __str__(self) -> str:
        return f"BranchDay({self.branch_id} {self.business_date})"


class CreditNoteVoid(models.Model):
    """Append-only audit event for voiding a credit note on open business day."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    credit_note = models.OneToOneField(
        "billing.CreditNote",
        on_delete=models.PROTECT,
        related_name="void_event",
        db_column="credit_note_id",
        db_index=False,
    )
    voided_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="credit_note_voids",
        db_column="voided_by_id",
        db_index=False,
    )
    voided_at = models.DateTimeField(auto_now_add=True)
    void_reason = models.TextField()
    void_business_date = models.DateField()
    restored_methods = models.JSONField(default=dict)

    class Meta:
        db_table = "billing_credit_note_void"

    def __str__(self) -> str:
        return f"CreditNoteVoid({self.credit_note_id} on {self.void_business_date})"


class InvoiceLineCancelled(models.Model):
    """Append-only event for cancelling an unperformed invoice line (Phase 6 Rule 6)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="cancelled_lines",
        db_column="invoice_id",
        db_index=False,
    )
    item = models.ForeignKey(
        "billing.InvoiceItem",
        on_delete=models.PROTECT,
        related_name="cancelled_events",
        db_column="item_id",
        db_index=False,
    )
    cancelled_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="cancelled_invoice_lines",
        db_column="cancelled_by_id",
        db_index=False,
    )
    cancelled_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    amount_removed = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "billing_invoice_line_cancelled"

    def __str__(self) -> str:
        return f"InvoiceLineCancelled({self.item_id} PKR {self.amount_removed})"


class InvoiceVoid(models.Model):
    """Append-only void record for a corrupted PAID invoice."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    invoice = models.OneToOneField(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="void_event",
        db_column="invoice_id",
        db_index=False,
    )
    voided_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="invoice_voids",
        db_column="voided_by_id",
        db_index=False,
    )
    voided_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    void_business_date = models.DateField()
    reversed_methods = models.JSONField(default=dict)

    class Meta:
        db_table = "billing_invoice_void"

    def __str__(self) -> str:
        return f"InvoiceVoid({self.invoice_id} on {self.void_business_date})"
