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
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
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


def _post_signed(url: str, raw_body: bytes, signature: str) -> tuple[int, bytes]:
    """POST the signed body; return (status_code, response_body).

    Raises WebhookTransportError on timeout / DNS / connection failure.
    Separated for testability — tests patch this instead of the network.
    """
    request = urllib.request.Request(
        url,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            signing.SIGNATURE_HEADER: signature,
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=WEBHOOK_POST_TIMEOUT_SECONDS
        ) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        # Non-2xx: the server answered; the caller decides retry vs sent.
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, body
    except Exception as exc:  # timeout, DNS, refused, ...
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
        row.status = WebhookDelivery.Status.PENDING
        row.attempts = row.attempts + 1
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
        row.status = WebhookDelivery.Status.PENDING
        row.attempts = row.attempts + 1
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
    ).order_by("next_attempt_at")
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
