from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q


class NotificationTemplate(models.Model):
    """
    Bilingual (en / ur) message templates per channel (Doc 02 §5.9, Doc 06 §1.4).
    Composite UNIQUE (key, locale, channel) via
    uq_notification_template_key_locale_channel. template_context_schema is
    one of the four sanctioned JSONB columns in Doc 02 §2.
    """

    class Locale(models.TextChoices):
        EN = "en", "English"
        UR = "ur", "Urdu"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    key = models.TextField(null=False, blank=False)
    locale = models.TextField(
        choices=Locale.choices,
        null=False,
        blank=False,
    )
    channel = models.TextField(
        choices=Channel.choices,
        null=False,
        blank=False,
    )
    subject = models.TextField(null=True, blank=True)  # noqa: DJ001
    body = models.TextField(null=False, blank=False)
    template_context_schema = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        db_table = "notification_template"
        constraints = [
            models.UniqueConstraint(
                fields=["key", "locale", "channel"],
                name="uq_notification_template_key_locale_channel",
            ),
            models.CheckConstraint(
                condition=Q(locale__in=["en", "ur"]),
                name="chk_notification_template_locale",
            ),
            models.CheckConstraint(
                condition=Q(channel__in=["email", "whatsapp"]),
                name="chk_notification_template_channel",
            ),
        ]

    def __str__(self) -> str:
        return f"NotificationTemplate {self.key} ({self.locale}/{self.channel})"


class Notification(models.Model):
    """
    Queued notification to a patient, partner, or staff member
    (Doc 02 §5.9, Doc 06 §9).
    - recipient_id is a plain UUID (no FK) because recipient table varies by
      recipient_type.
    - Partial UNIQUE on idempotency_key WHERE idempotency_key IS NOT NULL.
    """

    class RecipientType(models.TextChoices):
        PATIENT = "patient", "Patient"
        PARTNER = "partner", "Partner"
        STAFF = "staff", "Staff"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    template_key = models.TextField(null=True, blank=True)  # noqa: DJ001
    recipient_type = models.TextField(
        choices=RecipientType.choices,
        null=False,
        blank=False,
    )
    recipient_id = models.UUIDField(null=True, blank=True)
    channel = models.TextField(
        choices=Channel.choices,
        null=False,
        blank=False,
    )
    status = models.TextField(
        choices=Status.choices,
        default=Status.PENDING,
        db_default=Status.PENDING,
        null=False,
    )
    attempts = models.IntegerField(
        default=0,
        db_default=0,
        null=False,
    )
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)  # noqa: DJ001
    idempotency_key = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        db_table = "notification"
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uq_notification_idempotency_key",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PENDING", "SENT", "FAILED"]),
                name="chk_notification_status",
            ),
            models.CheckConstraint(
                condition=Q(recipient_type__in=["patient", "partner", "staff"]),
                name="chk_notification_recipient_type",
            ),
            models.CheckConstraint(
                condition=Q(channel__in=["email", "whatsapp"]),
                name="chk_notification_channel",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Notification {self.id} "
            f"({self.recipient_type}:{self.channel} - {self.status})"
        )
