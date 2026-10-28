from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q


class WebhookDelivery(models.Model):
    """
    Signed Django -> n8n webhook attempt with dedupe and retry state
    (Doc 02 §5.10, Doc 06 §5.1).
    - idempotency_key is NOT NULL with a full UNIQUE constraint
      (uq_webhook_delivery_idempotency_key).
    - payload_jsonb is a PostgreSQL jsonb column (sanctioned JSONB per Doc 02 §2).
    - Partial index idx_webhook_delivery_status_next_attempt_at WHERE status IN
      ('PENDING','FAILED').
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    event = models.TextField(null=False, blank=False)
    idempotency_key = models.TextField(null=False, blank=False)
    payload_jsonb = models.JSONField(null=False)
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
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        db_table = "webhook_delivery"
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                condition=Q(status__in=["PENDING", "FAILED"]),
                name="idx_webhook_delivery_status_next_attempt_at",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                name="uq_webhook_delivery_idempotency_key",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PENDING", "SENT", "FAILED"]),
                name="chk_webhook_delivery_status",
            ),
        ]

    def __str__(self) -> str:
        return f"WebhookDelivery {self.id} ({self.event} - {self.status})"
