import uuid

from django.db import models
from django.db.models import Q
from django.db.models.functions import Now


class Sample(models.Model):
    """One physical specimen, identified by its Code128 accession ID (Doc 02 §5.5).

    Includes A-2 rejection columns (rejection_reason_code, rejection_note).
    status is CHECK-constrained at the database level.
    """

    class Status(models.TextChoices):
        COLLECTED = "collected", "Collected"
        RECEIVED = "received", "Received"
        IN_PROCESS = "in_process", "In Process"
        READY = "ready", "Ready"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class RejectionReasonCode(models.TextChoices):
        UNLABELLED = "unlabelled", "Unlabelled"
        MISLABELLED = "mislabelled", "Mislabelled"
        HEMUSHED = "hemolyzed", "Hemolyzed"
        INSUFFICIENT_VOLUME = "insufficient_volume", "Insufficient Volume"
        WRONG_TUBE = "wrong_tube", "Wrong Tube"
        CLOTTED = "clotted", "Clotted"
        LIPEMIC = "lipemic", "Lipemic"
        DAMAGED_TRANSPORT = "damaged_transport", "Damaged Transport"
        BARCODE_ISSUE = "barcode_issue", "Barcode Issue"
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
        related_name="samples",
        db_column="invoice_id",
        db_index=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="samples",
        db_column="branch_id",
        db_index=False,
    )
    accession_id = models.TextField()
    status = models.TextField(
        choices=Status.choices,
        default=Status.COLLECTED,
        db_default=Status.COLLECTED,
    )
    collected_at = models.DateTimeField()
    collected_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="collected_samples",
        db_column="collected_by",
        db_index=False,
    )
    rejection_reason_code = models.TextField(  # noqa: DJ001
        choices=RejectionReasonCode.choices,
        null=True,
        blank=True,
    )
    rejection_note = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "sample"
        constraints = [
            models.UniqueConstraint(
                fields=["accession_id"],
                name="uq_sample_accession_id",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "collected",
                        "received",
                        "in_process",
                        "ready",
                        "rejected",
                        "cancelled",
                    ]
                ),
                name="chk_sample_status",
            ),
        ]
        indexes = [
            models.Index(
                fields=["invoice"],
                name="idx_sample_invoice_id",
            ),
            models.Index(
                fields=["branch"],
                name="idx_sample_branch_id",
            ),
            models.Index(
                fields=["collected_by"],
                name="idx_sample_collected_by",
            ),
            models.Index(
                fields=["branch", "status"],
                name="idx_sample_branch_id_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.accession_id} [{self.status}]"


class SampleTest(models.Model):
    """Link from a sample to the component tests ordered on it (Doc 02 §5.5).

    Has created_at only; unique on (sample_id, test_id).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    sample = models.ForeignKey(
        "samples.Sample",
        on_delete=models.PROTECT,
        related_name="sample_tests",
        db_column="sample_id",
        db_index=False,
    )
    invoice_item = models.ForeignKey(
        "billing.InvoiceItem",
        on_delete=models.PROTECT,
        related_name="sample_tests",
        db_column="invoice_item_id",
        db_index=False,
    )
    test = models.ForeignKey(
        "catalog.Test",
        on_delete=models.PROTECT,
        related_name="sample_tests",
        db_column="test_id",
        db_index=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "sample_test"
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "test"],
                name="uq_sample_test_sample_id_test_id",
            ),
        ]
        indexes = [
            models.Index(
                fields=["sample"],
                name="idx_sample_test_sample_id",
            ),
            models.Index(
                fields=["invoice_item"],
                name="idx_sample_test_invoice_item_id",
            ),
            models.Index(
                fields=["test"],
                name="idx_sample_test_test_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Sample({self.sample_id}) -> Test({self.test_id})"


class SampleEvent(models.Model):
    """Append-only timeline of everything that happened to a sample (Doc 02 §5.5, §6).

    event carries no database CHECK constraint by design so event names can evolve.
    Has created_at only; never updated_at or deleted_at.
    """

    class EventType(models.TextChoices):
        COLLECTED = "COLLECTED", "Collected"
        RECEIVED = "RECEIVED", "Received"
        IN_PROCESS = "IN_PROCESS", "In Process"
        REJECTED = "REJECTED", "Rejected"
        TRANSFERRED_IN = "TRANSFERRED_IN", "Transferred In"
        TRANSFERRED_OUT = "TRANSFERRED_OUT", "Transferred Out"
        TRANSFER_CANCELLED = "TRANSFER_CANCELLED", "Transfer Cancelled"
        TRANSFER_LOST = "TRANSFER_LOST", "Transfer Lost"
        READY = "READY", "Ready"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    sample = models.ForeignKey(
        "samples.Sample",
        on_delete=models.PROTECT,
        related_name="events",
        db_column="sample_id",
        db_index=False,
    )
    event = models.TextField(choices=EventType.choices)
    actor = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sample_events",
        db_column="actor_id",
        db_index=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sample_events",
        db_column="branch_id",
        db_index=False,
    )
    note = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "sample_event"
        indexes = [
            models.Index(
                fields=["sample"],
                name="idx_sample_event_sample_id",
            ),
            models.Index(
                fields=["actor"],
                name="idx_sample_event_actor_id",
            ),
            models.Index(
                fields=["branch"],
                name="idx_sample_event_branch_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Sample({self.sample_id}) {self.event}"


class SampleTransfer(models.Model):
    """Chain-of-custody record when a sample moves between branches (Doc 02 §5.5).

    Includes A-9 columns (status, dispatched_at, received_at).
    status is application-enforced per Doc 02 §2 and §5.5.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"
        LOST = "lost", "Lost"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    sample = models.ForeignKey(
        "samples.Sample",
        on_delete=models.PROTECT,
        related_name="transfers",
        db_column="sample_id",
        db_index=False,
    )
    from_branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="transfers_out",
        db_column="from_branch_id",
        db_index=False,
    )
    to_branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="transfers_in",
        db_column="to_branch_id",
        db_index=False,
    )
    transferred_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dispatched_transfers",
        db_column="transferred_by",
        db_index=False,
    )
    received_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="received_transfers",
        db_column="received_by",
        db_index=False,
    )
    status = models.TextField(
        choices=Status.choices,
        default=Status.OPEN,
        db_default=Status.OPEN,
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "sample_transfer"
        indexes = [
            models.Index(
                fields=["sample"],
                name="idx_sample_transfer_sample_id",
            ),
            models.Index(
                fields=["from_branch"],
                name="idx_sample_transfer_from_branch_id",
            ),
            models.Index(
                fields=["to_branch"],
                name="idx_sample_transfer_to_branch_id",
            ),
            models.Index(
                fields=["transferred_by"],
                name="idx_sample_transfer_transferred_by",
            ),
            models.Index(
                fields=["received_by"],
                name="idx_sample_transfer_received_by",
            ),
        ]

    def __str__(self) -> str:
        return f"Transfer({self.id}) Sample({self.sample_id}) [{self.status}]"
