"""LAB-45 (KAN-264): notification delivery tasks (Doc 06 §9, §12.9).

- notifications.retry_pending_deliveries: Beat sweep at minutes 11/26/41/56
  (Doc 10 §9 offsets), per-tenant fan-out (Doc 04 §13.2). Re-fires webhooks
  for FAILED notification rows with next_attempt_at <= now and
  attempts < 5. Rows whose last_error starts with "hard_bounce:" are
  skipped regardless of next_attempt_at (AU-40).
- notifications.send_notification: re-fires one notification's webhook to
  n8n with the same idempotency_key (IK-1), re-stamped timestamp and
  re-signed body (TS-2).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import requests
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.automation.services import (
    HARD_BOUNCE_PREFIX,
    MAX_NOTIFICATION_ATTEMPTS,
    SWEEP_BATCH_LIMIT,
    SWEEP_CLAIM_LEASE,
    notification_backoff,
)

logger = logging.getLogger(__name__)

RETRY_SWEEP_TASK_NAME = "notifications.retry_pending_deliveries"
SEND_TASK_NAME = "notifications.send_notification"

# Event catalogue (Doc 06 §6): template_key -> n8n event + callback route.
TEMPLATE_EVENT_MAP: dict[str, dict[str, str]] = {
    "sample_collected": {
        "event": "sample.collected",
        "callback_path": "/api/v1/webhooks/n8n/notification",
    },
    "sample_rejected": {
        "event": "sample.rejected",
        "callback_path": "/api/v1/webhooks/n8n/notification",
    },
    "settlement_ready": {
        "event": "settlement.approved",
        "callback_path": "/api/v1/webhooks/n8n/settlement-delivery",
    },
    "report_ready": {
        "event": "report.ready",
        "callback_path": "/api/v1/webhooks/n8n/report-delivery",
    },
    "report_link_resend": {
        "event": "report.ready",
        "callback_path": "/api/v1/webhooks/n8n/report-delivery",
    },
}


def _n8n_webhook_url() -> str:
    return os.environ.get("N8N_WEBHOOK_URL", "")


def _sign_payload(raw_body: bytes) -> str:
    """HMAC-SHA256 over the raw request body (Doc 06 §5.1)."""
    secret = os.environ.get("N8N_WEBHOOK_SECRET", "")
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _render_body(
    *, template_key: str, locale: str, channel: str, context: dict[str, Any]
) -> tuple[str | None, str]:
    """Render subject/body from notification_template; fallback on miss."""
    from apps.notifications.models import NotificationTemplate

    template = (
        NotificationTemplate.objects.filter(
            key=template_key, locale=locale, channel=channel
        )
        .order_by("id")
        .first()
    )
    if template is None:
        return None, f"[{template_key}]"
    body = template.body
    for key, value in context.items():
        body = body.replace("{{" + key + "}}", str(value))
    return template.subject, body


@shared_task(name=SEND_TASK_NAME)
def send_notification_task(schema_name: str, notification_id: str) -> dict[str, Any]:
    """Re-fire one notification's webhook to n8n (Doc 06 §5.1, TS-2).

    Same idempotency_key (IK-1), re-stamped timestamp and re-signed body
    (TS-2). Records the webhook_delivery row; the notification row itself
    only changes via callback (§9). Idempotent: a SENT webhook_delivery
    for the key is never re-sent.
    """
    from apps.automation.models import WebhookDelivery
    from apps.core.models import Tenant
    from apps.notifications.models import Notification

    with schema_context(schema_name):
        try:
            row = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            return {"status": "skipped", "reason": "row_gone"}

        # Idempotency: never re-send a webhook already accepted (IK-3).
        if WebhookDelivery.objects.filter(
            idempotency_key=row.idempotency_key,
            status=WebhookDelivery.Status.SENT,
        ).exists():
            return {"status": "skipped", "reason": "already_sent"}

        tenant = Tenant.objects.get(schema_name=schema_name)
        mapping = TEMPLATE_EVENT_MAP.get(row.template_key or "", {})
        event = mapping.get("event", row.template_key or "notification.send")
        callback_path = mapping.get(
            "callback_path", "/api/v1/webhooks/n8n/notification"
        )
        host = f"https://{tenant.slug}.labflow.app"
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        subject, body = _render_body(
            template_key=row.template_key or "",
            locale="en",
            channel=row.channel,
            context={},
        )
        payload: dict[str, Any] = {
            "event": event,
            "tenant_slug": tenant.slug,
            "callback_url": f"{host}{callback_path}",
            "idempotency_key": row.idempotency_key,
            "timestamp": timestamp,
            "data": {
                "template_key": row.template_key,
                "channel": row.channel,
                "recipient_type": row.recipient_type,
                "subject": subject,
                "body": body,
            },
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = _sign_payload(raw)

        with transaction.atomic():
            delivery, _ = WebhookDelivery.objects.get_or_create(
                idempotency_key=row.idempotency_key,
                defaults={
                    "event": event,
                    "payload_jsonb": payload,
                    "status": WebhookDelivery.Status.PENDING,
                },
            )

        url = _n8n_webhook_url()
        if not url:
            logger.warning(
                "notifications.send_notification: N8N_WEBHOOK_URL not set; "
                "webhook kept PENDING for %s",
                row.idempotency_key,
            )
            return {"status": "held", "reason": "no_n8n_url"}

        try:
            resp = requests.post(
                url,
                data=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-LabFlow-Signature": signature,
                },
                timeout=15,
            )
        except Exception as exc:  # network failure -> PENDING, sweep retries
            logger.warning(
                "notifications.send_notification: POST failed for %s: %s",
                row.idempotency_key,
                exc,
            )
            with transaction.atomic():
                delivery.attempts += 1
                delivery.next_attempt_at = timezone.now() + notification_backoff(
                    delivery.attempts
                )
                delivery.last_error = f"post_failed: {exc}"[:500]
                delivery.save(
                    update_fields=[
                        "attempts",
                        "next_attempt_at",
                        "last_error",
                        "updated_at",
                    ]
                )
            return {"status": "held", "reason": "post_failed"}

        with transaction.atomic():
            if 200 <= resp.status_code < 300:
                # AP-3: webhook accepted. The email outcome arrives by
                # callback; the notification row is untouched here.
                delivery.status = WebhookDelivery.Status.SENT
                delivery.next_attempt_at = None
                delivery.save(update_fields=["status", "next_attempt_at", "updated_at"])
                return {"status": "ok", "webhook": "sent"}
            delivery.attempts += 1
            delivery.status = WebhookDelivery.Status.FAILED
            delivery.next_attempt_at = timezone.now() + notification_backoff(
                delivery.attempts
            )
            delivery.last_error = f"n8n_http_{resp.status_code}"[:500]
            delivery.save(
                update_fields=[
                    "status",
                    "attempts",
                    "next_attempt_at",
                    "last_error",
                    "updated_at",
                ]
            )
            return {"status": "held", "reason": f"http_{resp.status_code}"}


@shared_task(name=RETRY_SWEEP_TASK_NAME)
def retry_pending_deliveries_task() -> dict[str, Any]:
    """Beat sweep (Doc 06 §12.9, AU-20, AU-21, AU-40).

    Per-tenant fan-out (Doc 04 §13.2): re-fires webhooks for FAILED
    notification rows with next_attempt_at <= now and attempts < 5.
    Rows whose last_error starts with "hard_bounce:" are skipped
    regardless of next_attempt_at (AU-40) — the sentinel alone stops
    retries.

    Claim race: each due row is claimed with SELECT FOR UPDATE ...
    SKIP LOCKED and its next_attempt_at is pushed out by the claim lease
    BEFORE the send task is enqueued.
    """
    from apps.core.models import Tenant
    from apps.notifications.models import Notification

    now = timezone.now()
    requeued = 0
    per_tenant: dict[str, int] = {}
    skipped_hard_bounce = 0
    tenants = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
    for tenant in tenants:
        schema_name = tenant.schema_name
        try:
            with schema_context(schema_name):
                with transaction.atomic():
                    candidates = list(
                        Notification.objects.select_for_update(skip_locked=True)
                        .filter(
                            status=Notification.Status.FAILED,
                            next_attempt_at__lte=now,
                            attempts__lt=MAX_NOTIFICATION_ATTEMPTS,
                        )
                        .order_by("next_attempt_at")[:SWEEP_BATCH_LIMIT]
                    )
                    due_ids: list[str] = []
                    for notif in candidates:
                        # AU-40: the hard_bounce: sentinel stops retries
                        # even if next_attempt_at was left set by a bug.
                        if (notif.last_error or "").startswith(HARD_BOUNCE_PREFIX):
                            skipped_hard_bounce += 1
                            continue
                        notif.next_attempt_at = now + SWEEP_CLAIM_LEASE
                        notif.save(update_fields=["next_attempt_at", "updated_at"])
                        due_ids.append(str(notif.id))
                for notif_id in due_ids:
                    send_notification_task.delay(schema_name, notif_id)
                requeued += len(due_ids)
                per_tenant[schema_name] = len(due_ids)
                if due_ids:
                    logger.info(
                        "notifications.retry_pending_deliveries: requeued %d in %s",
                        len(due_ids),
                        schema_name,
                    )
        except Exception:
            logger.exception(
                "notifications.retry_pending_deliveries: failed for schema %s",
                schema_name,
            )
    return {
        "status": "ok",
        "requeued": requeued,
        "tenants": per_tenant,
        "skipped_hard_bounce": skipped_hard_bounce,
    }
