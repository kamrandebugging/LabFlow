"""Outbound webhook engine (Doc 06 §5.1–§5.3, §5.5, §8.4).

Flow per §5.1, in order:
1. Write the ``webhook_delivery`` row first (PENDING, attempts=0) and store
   the payload, unchanged, in ``payload_jsonb``.
2. POST the payload to the n8n webhook URL, signed (HMAC-SHA256 over the raw
   body in ``X-LabFlow-Signature``).
3. 2xx → SENT. Non-2xx/timeout → PENDING with attempts+1 and next_attempt_at
   set; the Beat sweep retries it (§5.2, §12).

Retry semantics (§5.2 TS-2): the sweep re-stamps ``timestamp`` at send time
and re-signs; the stored ``payload_jsonb`` keeps the original timestamp for
audit. The ``idempotency_key`` never changes.

Security: secrets come from env only (Doc 02 §8) and are never logged.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.automation import payloads, signing
from apps.automation.models import WebhookDelivery

logger = logging.getLogger(__name__)

CALLBACK_KEY_HEADER = "X-LabFlow-Callback-Key"

# Retry backoff: base 5 minutes, doubling per attempt, capped at 2 hours.
# The exact curve is an implementation detail — the doc fixes the sweep
# cadence (Doc 10 §9: minutes 3/18/33/48), not the per-row delay.
RETRY_BASE_DELAY = timedelta(minutes=5)
RETRY_MAX_DELAY = timedelta(hours=2)
# SE-44: bounded retries, then a terminal FAILED row (dead-letter analogue).
WEBHOOK_MAX_ATTEMPTS = 5

# HTTP timeout for the outbound POST (seconds).
WEBHOOK_POST_TIMEOUT_SECONDS = 15


class WebhookConfigurationError(Exception):
    """Raised when webhook secrets are missing — fail fast, before any row."""


class WebhookTransportError(Exception):
    """Raised when the outbound POST cannot complete (timeout/DNS/etc.)."""


def get_webhook_secret() -> str:
    """Return N8N_WEBHOOK_SECRET; raise if unset (never sign with empty key)."""
    secret = getattr(settings, "N8N_WEBHOOK_SECRET", "") or ""
    if not secret:
        raise WebhookConfigurationError("N8N_WEBHOOK_SECRET is not configured")
    return secret


def webhook_url_for_event(event: str) -> str | None:
    """Return the n8n webhook URL for an event, or None if unconfigured.

    The event→URL map lives in settings.N8N_WEBHOOK_URLS (Doc 10 holds n8n
    configuration values). Unknown events return None so the sweep skips
    them loudly instead of failing.
    """
    urls = getattr(settings, "N8N_WEBHOOK_URLS", None) or {}
    return urls.get(event)


def retry_delay(attempts: int) -> timedelta:
    """Exponential backoff for the next retry attempt."""
    delay = RETRY_BASE_DELAY * (2 ** max(0, attempts - 1))
    return min(delay, RETRY_MAX_DELAY)


def _validate_whatsapp_url(url: str) -> None:
    """Only https://wa.me/... may be stored/broadcast (API10 G10-4)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "wa.me":
        raise CallbackError("invalid_whatsapp_url", 422)


def _post_signed(url: str, raw_body: bytes, signature: str) -> tuple[int, bytes]:
    """POST the signed body through the shared safe fetcher.

    Raises WebhookTransportError on timeout / DNS / connection failure or an
    unsafe destination (API7 G-11). Separated for testability — tests patch
    this instead of the network.
    """
    from apps.core.safe_fetch import SafeFetchError, UnsafeURLError
    from apps.core.safe_fetch import post as safe_post

    try:
        response = safe_post(
            url,
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                signing.SIGNATURE_HEADER: signature,
            },
            timeout=WEBHOOK_POST_TIMEOUT_SECONDS,
        )
        return response.status_code, response.content
    except (SafeFetchError, UnsafeURLError) as exc:
        raise WebhookTransportError(str(exc)) from exc


def _send_row(
    row: WebhookDelivery,
    webhook_url: str,
    secret: str,
    *,
    restamp: bool,
) -> None:
    """Send one delivery row; update its status in place.

    Args:
        restamp: True on sweep retries — re-stamp timestamp at send time and
            re-sign (§5.2 TS-2). False on first send (payload is already fresh).
    """
    stored = dict(row.payload_jsonb)
    if restamp:
        wire_payload = dict(stored)
        wire_payload["timestamp"] = payloads.utc_now_iso()
    else:
        wire_payload = stored
    raw_body = payloads.serialize_payload(wire_payload)
    signature = signing.sign_payload(raw_body, secret)

    try:
        status_code, _ = _post_signed(webhook_url, raw_body, signature)
    except WebhookTransportError as exc:
        row.attempts = row.attempts + 1
        if row.attempts >= WEBHOOK_MAX_ATTEMPTS:
            row.status = WebhookDelivery.Status.FAILED
            row.next_attempt_at = None
        else:
            row.status = WebhookDelivery.Status.PENDING
            row.next_attempt_at = timezone.now() + retry_delay(row.attempts)
        row.last_error = f"transport_error: {exc}"
        row.save(
            update_fields=[
                "status",
                "attempts",
                "next_attempt_at",
                "last_error",
                "updated_at",
            ]
        )
        logger.warning(
            "webhook_delivery %s transport failure (attempt %d)",
            row.idempotency_key,
            row.attempts,
        )
        return

    if 200 <= status_code < 300:
        row.status = WebhookDelivery.Status.SENT
        row.next_attempt_at = None
        row.last_error = None
        row.save(
            update_fields=["status", "next_attempt_at", "last_error", "updated_at"]
        )
        logger.info(
            "webhook_delivery %s sent (event=%s)",
            row.idempotency_key,
            row.event,
        )
    else:
        row.attempts = row.attempts + 1
        if row.attempts >= WEBHOOK_MAX_ATTEMPTS:
            row.status = WebhookDelivery.Status.FAILED
            row.next_attempt_at = None
        else:
            row.status = WebhookDelivery.Status.PENDING
            row.next_attempt_at = timezone.now() + retry_delay(row.attempts)
        row.last_error = f"http_{status_code}"
        row.save(
            update_fields=[
                "status",
                "attempts",
                "next_attempt_at",
                "last_error",
                "updated_at",
            ]
        )
        logger.warning(
            "webhook_delivery %s got HTTP %d (attempt %d)",
            row.idempotency_key,
            status_code,
            row.attempts,
        )


def emit_webhook(
    *,
    event: str,
    tenant_slug: str,
    webhook_url: str,
    callback_url: str,
    data: dict[str, Any],
    idempotency_key: str | None = None,
) -> WebhookDelivery:
    """Emit one outbound webhook (Doc 06 §5.1).

    The delivery row is written FIRST (PENDING, attempts=0) with the payload
    stored unchanged in payload_jsonb; only then is the POST attempted. If
    n8n vanished, every unsent message remains a row waiting (Doc 06 §1.1).
    """
    secret = get_webhook_secret()  # fail fast — before any row is written
    key = idempotency_key or str(uuid.uuid4())
    payload = payloads.build_webhook_payload(
        event=event,
        tenant_slug=tenant_slug,
        callback_url=callback_url,
        idempotency_key=key,
        data=data,
    )
    # next_attempt_at is set at creation so that a crash between the row
    # write and the POST can never strand a PENDING row the sweep ignores
    # (NULL next_attempt_at is never <= now). A successful send clears it.
    row = WebhookDelivery.objects.create(
        event=event,
        idempotency_key=key,
        payload_jsonb=payload,
        status=WebhookDelivery.Status.PENDING,
        attempts=0,
        next_attempt_at=timezone.now() + retry_delay(1),
    )
    _send_row(row, webhook_url, secret, restamp=False)
    row.refresh_from_db()
    return row


def retry_due_deliveries(
    *,
    tenant_slug: str,
    webhook_url: str,
    now: datetime | None = None,
) -> int:
    """Beat sweep: retry PENDING/FAILED rows whose next_attempt_at is due.

    Re-stamps timestamp at send time and re-signs; the idempotency key never
    changes (§5.2 TS-2). Returns the number of rows attempted.
    """
    secret = get_webhook_secret()
    at = now or timezone.now()
    due = WebhookDelivery.objects.filter(
        status__in=[
            WebhookDelivery.Status.PENDING,
            WebhookDelivery.Status.FAILED,
        ],
        next_attempt_at__lte=at,
    ).order_by("next_attempt_at")[:100]
    attempted = 0
    for row in due:
        _send_row(row, webhook_url, secret, restamp=True)
        attempted += 1
    if attempted:
        logger.info(
            "webhook retry sweep attempted %d deliveries (tenant=%s)",
            attempted,
            tenant_slug,
        )
    return attempted


def verify_callback_key(presented: str) -> bool:
    """Check the X-LabFlow-Callback-Key with dual-accept during rotation.

    Doc 06 §5.5: while N8N_CALLBACK_KEY_NEXT is set, both keys are accepted.
    After promotion (NEXT cleared), the old key is rejected (AU-25).
    Constant-time comparison; empty presented key never matches.
    """
    if not presented:
        return False
    current = getattr(settings, "N8N_CALLBACK_KEY", "") or ""
    nxt = getattr(settings, "N8N_CALLBACK_KEY_NEXT", "") or ""
    if current and hmac.compare_digest(presented, current):
        return True
    return bool(nxt and hmac.compare_digest(presented, nxt))


def extract_message_id(body: dict[str, Any]) -> str | None:
    """Return the optional callback message_id for logging.

    Doc 06 §8.4 (OQ-48): message_id is accepted and logged with the
    callback, but never persisted — WebhookDelivery has no such column.
    """
    value = body.get("message_id")
    return str(value) if value else None


HARD_BOUNCE_PREFIX = "hard_bounce:"

# Doc 01 §13 / Doc 05 DL-5: 5 retries, backoff from 30 seconds to 30 minutes.
MAX_NOTIFICATION_ATTEMPTS = 5

# Claim lease for the retry sweep: two overlapping Beat runs cannot
# double-enqueue a row (same pattern as reports.retry_failed_deliveries).
SWEEP_CLAIM_LEASE = timedelta(minutes=30)
SWEEP_BATCH_LIMIT = 100

CALLBACK_STATUSES = ("SENT", "FAILED")


class CallbackError(Exception):
    """Carries the Doc 03 §6.1-shaped error for callback endpoints."""

    def __init__(
        self,
        error_code: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


def notification_backoff(attempts: int) -> timedelta:
    """Row-level retry backoff ladder: 30s -> 2m -> 8m -> 15m -> 30m."""
    ladder = [30, 120, 480, 900, 1800]
    return timedelta(seconds=ladder[min(max(attempts, 1) - 1, 4)])


def _is_hard_bounce(last_error: str | None) -> bool:
    return bool(last_error) and str(last_error).startswith(HARD_BOUNCE_PREFIX)


def _validate_status(status: str | None) -> str:
    if status not in CALLBACK_STATUSES:
        # DO-10: OPENED (or anything else) is never accepted on a callback.
        raise CallbackError("invalid_status", 422)
    return status


def _audit_callback(
    *,
    action: str,
    entity_type: str,
    entity_id: Any,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    # Local import: accounts is the canonical home of AuditLog.
    from apps.accounts.models import AuditLog

    AuditLog.objects.create(
        actor_id=None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_jsonb=before,
        after_jsonb=after,
        ip=None,
        user_agent="n8n-callback",
    )


def apply_notification_callback(
    *,
    idempotency_key: str,
    status: str,
    last_error: str | None,
) -> dict[str, Any]:
    """Apply the §9 outcome map to a notification row.

    Idempotent on (idempotency_key, outcome): a repeated identical outcome
    returns the row's current state and changes nothing (CB-1).
    """
    from apps.notifications.models import Notification

    status = _validate_status(status)
    if status == "FAILED" and not last_error:
        raise CallbackError("last_error_required", 422)

    with transaction.atomic():
        try:
            row = Notification.objects.select_for_update().get(
                idempotency_key=idempotency_key
            )
        except Notification.DoesNotExist:
            # §12.4: the callback outran the outbound write.
            raise CallbackError("row_not_ready", 409) from None

        before = {"status": row.status, "attempts": row.attempts}

        if status == "SENT":
            if row.status == Notification.Status.SENT:
                return {"idempotency_key": idempotency_key, "status": "SENT"}
            if row.status == Notification.Status.FAILED and (
                _is_hard_bounce(row.last_error)
                or row.attempts >= MAX_NOTIFICATION_ATTEMPTS
            ):
                # AU-13: a SENT for a row already final as failed.
                raise CallbackError("state_conflict", 409)
            row.status = Notification.Status.SENT
            row.next_attempt_at = None
            row.save(update_fields=["status", "next_attempt_at", "updated_at"])
            _audit_callback(
                action="webhook.notification_callback",
                entity_type="notification",
                entity_id=row.id,
                before=before,
                after={"status": "SENT"},
            )
            return {"idempotency_key": idempotency_key, "status": "SENT"}

        # status == FAILED
        if row.status == Notification.Status.SENT:
            raise CallbackError("state_conflict", 409)
        if row.status == Notification.Status.FAILED and row.last_error == (
            last_error or ""
        ):
            # Same outcome delivered twice: idempotent no-op (CB-1).
            return {"idempotency_key": idempotency_key, "status": "FAILED"}
        row.attempts += 1
        row.last_error = last_error or ""
        if _is_hard_bounce(last_error) or row.attempts >= MAX_NOTIFICATION_ATTEMPTS:
            # DO-6 / DO-4: terminal failure, no further retries.
            row.status = Notification.Status.FAILED
            row.next_attempt_at = None
        else:
            row.status = Notification.Status.FAILED
            row.next_attempt_at = timezone.now() + notification_backoff(row.attempts)
        row.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "next_attempt_at",
                "updated_at",
            ]
        )
        _audit_callback(
            action="webhook.notification_callback",
            entity_type="notification",
            entity_id=row.id,
            before=before,
            after={
                "status": "FAILED",
                "attempts": row.attempts,
                "hard_bounce": _is_hard_bounce(last_error),
            },
        )
        return {"idempotency_key": idempotency_key, "status": "FAILED"}


def apply_report_delivery_callback(
    *,
    idempotency_key: str,
    channel: str,
    status: str,
    whatsapp_url: str | None,
    last_error: str | None,
) -> dict[str, Any]:
    """Apply the §9 outcome map to a report_delivery row."""
    from apps.reports.models import ReportDelivery

    status = _validate_status(status)
    if status == "FAILED" and not last_error:
        raise CallbackError("last_error_required", 422)

    with transaction.atomic():
        try:
            row = ReportDelivery.objects.select_for_update().get(
                idempotency_key=idempotency_key
            )
        except ReportDelivery.DoesNotExist:
            raise CallbackError("row_not_ready", 409) from None

        if channel not in (
            ReportDelivery.Channel.EMAIL,
            ReportDelivery.Channel.WHATSAPP,
        ):
            raise CallbackError("invalid_channel", 422)
        if channel != row.channel:
            raise CallbackError("state_conflict", 409)

        before = {"status": row.status, "attempts": row.attempts}

        if status == "SENT":
            if row.status == ReportDelivery.Status.SENT:
                return {"idempotency_key": idempotency_key, "status": "SENT"}
            if row.status == ReportDelivery.Status.BOUNCED:
                # AU-13: final as hard-bounced.
                raise CallbackError("state_conflict", 409)
            if channel == ReportDelivery.Channel.WHATSAPP:
                if not whatsapp_url:
                    raise CallbackError("whatsapp_url_required", 422)
                _validate_whatsapp_url(whatsapp_url)
                row.whatsapp_url = whatsapp_url
                update_fields = [
                    "status",
                    "whatsapp_url",
                    "next_attempt_at",
                    "updated_at",
                ]
            else:
                update_fields = ["status", "next_attempt_at", "updated_at"]
            row.status = ReportDelivery.Status.SENT
            row.next_attempt_at = None
            row.save(update_fields=update_fields)
            _audit_callback(
                action="webhook.report_delivery_callback",
                entity_type="report_delivery",
                entity_id=row.id,
                before=before,
                after={"status": "SENT", "channel": channel},
            )
            return {"idempotency_key": idempotency_key, "status": "SENT"}

        # status == FAILED
        if row.status == ReportDelivery.Status.SENT:
            raise CallbackError("state_conflict", 409)
        if row.status == ReportDelivery.Status.BOUNCED:
            raise CallbackError("state_conflict", 409)
        if row.status == ReportDelivery.Status.FAILED and row.last_error == (
            last_error or ""
        ):
            return {"idempotency_key": idempotency_key, "status": "FAILED"}
        row.attempts += 1
        row.last_error = last_error or ""
        if _is_hard_bounce(last_error):
            # DO-9: hard bounce on a report email ends the row as BOUNCED.
            row.status = ReportDelivery.Status.BOUNCED
            row.next_attempt_at = None
            new_status = "BOUNCED"
        elif row.attempts >= MAX_NOTIFICATION_ATTEMPTS:
            row.status = ReportDelivery.Status.FAILED
            row.next_attempt_at = None
            new_status = "FAILED"
        else:
            row.status = ReportDelivery.Status.FAILED
            row.next_attempt_at = timezone.now() + notification_backoff(row.attempts)
            new_status = "FAILED"
        row.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "next_attempt_at",
                "updated_at",
            ]
        )
        _audit_callback(
            action="webhook.report_delivery_callback",
            entity_type="report_delivery",
            entity_id=row.id,
            before=before,
            after={"status": new_status, "attempts": row.attempts},
        )
        return {"idempotency_key": idempotency_key, "status": new_status}


def apply_settlement_callback(
    *,
    settlement_id: str,
    idempotency_key: str,
    status: str,
    last_error: str | None,
) -> dict[str, Any]:
    """Apply the §9 outcome map to a settlement's notification row.

    On SENT, the settlement moves APPROVED -> SENT in the SAME transaction
    (Doc 05 §7.3). If the settlement is not APPROVED, the callback returns
    409 state_conflict and the notification row is left untouched for staff
    to inspect — a delivery fact is never forced onto a wrong-state
    settlement.
    """
    from apps.notifications.models import Notification
    from apps.partners.models import Settlement

    status = _validate_status(status)
    if status == "FAILED" and not last_error:
        raise CallbackError("last_error_required", 422)

    with transaction.atomic():
        try:
            row = Notification.objects.select_for_update().get(
                idempotency_key=idempotency_key
            )
        except Notification.DoesNotExist:
            raise CallbackError("row_not_ready", 409) from None

        try:
            settlement = Settlement.objects.select_for_update().get(id=settlement_id)
        except Settlement.DoesNotExist:
            raise CallbackError("not_found", 404) from None

        before = {
            "notification_status": row.status,
            "settlement_status": settlement.status,
        }

        if status == "SENT":
            if settlement.status == Settlement.Status.SENT and (
                row.status == Notification.Status.SENT
            ):
                # AU-34: delivered twice — exactly-once settlement move.
                return {
                    "idempotency_key": idempotency_key,
                    "status": "SENT",
                    "settlement_status": "SENT",
                }
            if settlement.status != Settlement.Status.APPROVED:
                raise CallbackError("state_conflict", 409)
            row.status = Notification.Status.SENT
            row.next_attempt_at = None
            row.save(update_fields=["status", "next_attempt_at", "updated_at"])
            settlement.status = Settlement.Status.SENT
            settlement.save(update_fields=["status", "updated_at"])
            _audit_callback(
                action="webhook.settlement_delivery_callback",
                entity_type="settlement",
                entity_id=settlement.id,
                before=before,
                after={"settlement_status": "SENT"},
            )
            return {
                "idempotency_key": idempotency_key,
                "status": "SENT",
                "settlement_status": "SENT",
            }

        # status == FAILED: same map as a plain notification; the
        # settlement stays APPROVED (Doc 05 DL-5).
        if row.status == Notification.Status.SENT:
            raise CallbackError("state_conflict", 409)
        if row.status == Notification.Status.FAILED and row.last_error == (
            last_error or ""
        ):
            return {
                "idempotency_key": idempotency_key,
                "status": "FAILED",
                "settlement_status": settlement.status,
            }
        row.attempts += 1
        row.last_error = last_error or ""
        if _is_hard_bounce(last_error) or row.attempts >= MAX_NOTIFICATION_ATTEMPTS:
            row.next_attempt_at = None
        else:
            row.next_attempt_at = timezone.now() + notification_backoff(row.attempts)
        row.status = Notification.Status.FAILED
        row.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "next_attempt_at",
                "updated_at",
            ]
        )
        _audit_callback(
            action="webhook.settlement_delivery_callback",
            entity_type="settlement",
            entity_id=settlement.id,
            before=before,
            after={
                "notification_status": "FAILED",
                "settlement_status": settlement.status,
            },
        )
        return {
            "idempotency_key": idempotency_key,
            "status": "FAILED",
            "settlement_status": settlement.status,
        }
