import uuid

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now


class Report(models.Model):
    """
    Patient-facing report for one sample in v1 (Doc 02 §5.7, §11; OQ-15 resolved).
    Voided via status='void'; never soft-deleted.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINAL = "final", "Final"
        AMENDED = "amended", "Amended"
        VOID = "void", "Void"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    sample = models.ForeignKey(
        "samples.Sample",
        on_delete=models.PROTECT,
        related_name="reports",
        db_column="sample_id",
        db_index=False,
    )
    status = models.TextField(
        choices=Status.choices,
        default=Status.DRAFT,
        db_default=Status.DRAFT,
    )
    current_version = models.IntegerField(
        default=0,
        db_default=0,
    )
    finalised_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "report"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "draft",
                        "final",
                        "amended",
                        "void",
                    ]
                ),
                name="chk_report_status",
            ),
        ]
        indexes = [
            models.Index(
                fields=["sample"],
                name="idx_report_sample_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Report({self.id}) v{self.current_version} [{self.status}]"


class ReportVersion(models.Model):
    """
    One immutable rendered version of a report PDF in object storage (Doc 02 §5.7, §6).
    Append-only: has created_at only, never updated_at or deleted_at.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    report = models.ForeignKey(
        "reports.Report",
        on_delete=models.PROTECT,
        related_name="versions",
        db_column="report_id",
        db_index=False,
    )
    version = models.IntegerField()
    pdf_key = models.TextField()
    generated_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="generated_report_versions",
        db_column="generated_by",
        db_index=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "report_version"
        constraints = [
            models.CheckConstraint(
                condition=Q(version__gt=0),
                name="chk_report_version_version_pos",
            ),
            models.UniqueConstraint(
                fields=["report", "version"],
                name="uq_report_version_report_id_version",
            ),
            models.UniqueConstraint(
                fields=["pdf_key"],
                name="uq_report_version_pdf_key",
            ),
        ]
        indexes = [
            models.Index(
                fields=["report"],
                name="idx_report_version_report_id",
            ),
            models.Index(
                fields=["generated_by"],
                name="idx_report_version_generated_by",
            ),
        ]

    def __str__(self) -> str:
        return f"ReportVersion({self.report_id} v{self.version})"


class ReportDelivery(models.Model):
    """
    One delivery attempt of a report link to the patient via n8n (Doc 02 §5.7).
    Includes whatsapp_url and partial retry index WHERE status IN ('PENDING','FAILED').
    """

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        BOUNCED = "BOUNCED", "Bounced"
        OPENED = "OPENED", "Opened"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    report = models.ForeignKey(
        "reports.Report",
        on_delete=models.PROTECT,
        related_name="deliveries",
        db_column="report_id",
        db_index=False,
    )
    channel = models.TextField(choices=Channel.choices)
    status = models.TextField(
        choices=Status.choices,
        default=Status.PENDING,
        db_default=Status.PENDING,
    )
    whatsapp_url = models.TextField(null=True, blank=True)  # noqa: DJ001
    attempts = models.IntegerField(
        default=0,
        db_default=0,
    )
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "report_delivery"
        constraints = [
            models.CheckConstraint(
                condition=Q(channel__in=["email", "whatsapp"]),
                name="chk_report_delivery_channel",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "PENDING",
                        "SENT",
                        "FAILED",
                        "BOUNCED",
                        "OPENED",
                    ]
                ),
                name="chk_report_delivery_status",
            ),
        ]
        indexes = [
            models.Index(
                fields=["report"],
                name="idx_report_delivery_report_id",
            ),
            models.Index(
                fields=["status", "next_attempt_at"],
                condition=Q(status__in=["PENDING", "FAILED"]),
                name="idx_report_delivery_status_next_attempt_at",
            ),
        ]

    def __str__(self) -> str:
        return f"ReportDelivery({self.id}) [{self.channel}:{self.status}]"


class ReportAccessToken(models.Model):
    """
    Hashed token behind a patient's signed report link (Doc 02 §5.7, §9, §14).
    Stores only token_hash (argon2); plain token is never stored.
    Revoked via revoked_at; never soft-deleted.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    report = models.ForeignKey(
        "reports.Report",
        on_delete=models.PROTECT,
        related_name="access_tokens",
        db_column="report_id",
        db_index=False,
    )
    token_hash = models.TextField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "report_access_token"
        constraints = [
            models.UniqueConstraint(
                fields=["token_hash"],
                name="uq_report_access_token_token_hash",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="chk_report_access_token_expires_after_created",
            ),
        ]
        indexes = [
            models.Index(
                fields=["report"],
                name="idx_report_access_token_report_id",
            ),
        ]

    def __str__(self) -> str:
        return f"ReportAccessToken({self.id}) Report({self.report_id})"
