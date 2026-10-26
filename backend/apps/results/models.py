import uuid

from django.db import models
from django.db.models import Q
from django.db.models.functions import Now


class Result(models.Model):
    """
    One measured value for one test on one sample (Doc 02 §5.6).
    value is stored as text verbatim (OQ-25 resolved).
    flag is nullable by design (NULL = qualitative or unparseable; never guessed).
    status is CHECK-constrained at the database level, including 'withdrawn'.
    """

    class Flag(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        ENTERED = "entered", "Entered"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        AMENDED = "amended", "Amended"
        WITHDRAWN = "withdrawn", "Withdrawn"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    sample = models.ForeignKey(
        "samples.Sample",
        on_delete=models.PROTECT,
        related_name="results",
        db_column="sample_id",
        db_index=False,
    )
    test = models.ForeignKey(
        "catalog.Test",
        on_delete=models.PROTECT,
        related_name="results",
        db_column="test_id",
        db_index=False,
    )
    value = models.TextField()
    unit = models.TextField(null=True, blank=True)  # noqa: DJ001
    flag = models.TextField(  # noqa: DJ001
        choices=Flag.choices,
        null=True,
        blank=True,
    )
    status = models.TextField(
        choices=Status.choices,
        default=Status.ENTERED,
        db_default=Status.ENTERED,
    )
    entered_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="entered_results",
        db_column="entered_by",
        db_index=False,
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
        db_table = "result"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "entered",
                        "approved",
                        "rejected",
                        "amended",
                        "withdrawn",
                    ]
                ),
                name="chk_result_status",
            ),
        ]
        indexes = [
            models.Index(
                fields=["sample"],
                name="idx_result_sample_id",
            ),
            models.Index(
                fields=["test"],
                name="idx_result_test_id",
            ),
            models.Index(
                fields=["entered_by"],
                name="idx_result_entered_by",
            ),
        ]

    def __str__(self) -> str:
        return f"Result({self.id}) Sample({self.sample_id}) [{self.status}]"


class ResultApproval(models.Model):
    """
    Pathologist's sign-off or rejection of a result (Doc 02 §5.6).
    Has created_at only; a changed decision is a new approval row.
    """

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    result = models.ForeignKey(
        "results.Result",
        on_delete=models.PROTECT,
        related_name="approvals",
        db_column="result_id",
        db_index=False,
    )
    pathologist = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="result_approvals",
        db_column="pathologist_id",
        db_index=False,
    )
    decision = models.TextField(choices=Decision.choices)
    note = models.TextField(null=True, blank=True)  # noqa: DJ001
    range_override = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "result_approval"
        indexes = [
            models.Index(
                fields=["result"],
                name="idx_result_approval_result_id",
            ),
            models.Index(
                fields=["pathologist"],
                name="idx_result_approval_pathologist_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Approval({self.id}) Result({self.result_id}) [{self.decision}]"


class CriticalNotification(models.Model):
    """
    Append-only record that a critical result was notified (Doc 02 §5.6, §6; A-3).
    Has created_at only; never updated_at or deleted_at.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    result = models.ForeignKey(
        "results.Result",
        on_delete=models.PROTECT,
        related_name="critical_notifications",
        db_column="result_id",
        db_index=False,
    )
    notified_name = models.TextField()
    notified_at = models.DateTimeField()
    read_back = models.BooleanField(default=False, db_default=False)
    recorded_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        related_name="recorded_critical_notifications",
        db_column="recorded_by",
        db_index=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "critical_notification"
        indexes = [
            models.Index(
                fields=["result"],
                name="idx_critical_notification_result_id",
            ),
            models.Index(
                fields=["recorded_by"],
                name="idx_critical_notification_recorded_by",
            ),
        ]

    def __str__(self) -> str:
        return f"CriticalNotification({self.id}) Result({self.result_id})"
