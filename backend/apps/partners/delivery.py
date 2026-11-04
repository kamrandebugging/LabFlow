"""Settlement delivery service (Doc 05 §9, §7.7 ST-21, KAN-262 / LAB-43).

Delivery path (DL-2, DL-3):
- dispatch_settlement_delivery() records the INTENT: a Notification row
  (template_key='settlement_ready', recipient_type='partner', channel='email',
  status PENDING) plus a webhook_delivery row carrying the signed n8n event.
- A Celery task hands the event to n8n (Doc 06 owns the workflow internals).
- SENT is set by the callback only — never assumed at send time.
- partner email missing (ST-21): notification FAILED with
  last_error='partner_email_missing'; the settlement stays APPROVED.

Thin-service rule: no business logic in views; views call this module.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AuditLog, StaffUser
from apps.automation.models import WebhookDelivery
from apps.notifications.models import Notification
from apps.partners.models import Settlement

logger = logging.getLogger(__name__)

# Doc 01 §13 notifications queue policy: 5 retries, 30 s to 30 min.
DELIVERY_MAX_ATTEMPTS = 5
DELIVERY_BACKOFF_SECONDS = (30, 120, 600, 1800, 1800)

TEMPLATE_KEY = "settlement_ready"
WEBHOOK_EVENT = "settlement.delivery_requested"
EMAIL_MISSING_ERROR = "partner_email_missing"

# Claim lease so overlapping 15-min beat runs cannot double-enqueue (§10).
SWEEP_CLAIM_LEASE_SECONDS = 120
SWEEP_BATCH_LIMIT = 200


class SettlementDeliveryError(Exception):
    """Delivery-domain error carrying an HTTP status + machine code."""

    __test__ = False
    status_code: int = 422
    error_code: str = "settlement_delivery_error"

    def __init__(self, message: str = "", *, details: Any = None) -> None:
        super().__init__(message or self.error_code)
        self.details = details


class InvalidStateTransitionError(SettlementDeliveryError):
    status_code = 409
    error_code = "invalid_state_transition"


class PartnerEmailMissingError(SettlementDeliveryError):
    status_code = 422
    error_code = "partner_email_missing"


class InvalidSignatureError(SettlementDeliveryError):
    status_code = 403
    error_code = "invalid_signature"


class TenantMismatchError(SettlementDeliveryError):
    status_code = 403
    error_code = "tenant_mismatch"


class SettlementNotFoundError(SettlementDeliveryError):
    status_code = 404
    error_code = "not_found"


def _webhook_secret() -> str:
    return str(
        getattr(
            settings,
            "N8N_WEBHOOK_SECRET",
            getattr(settings, "SECRET_KEY", ""),
        )
    )


def _sign_payload(body: dict[str, Any]) -> str:
    """HMAC-SHA256 over the canonical JSON body (Doc 01 §13)."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        _webhook_secret().encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _tenant_slug() -> str:
    # Delivery always runs inside an explicit schema_context, so the
    # connection's schema is unambiguous (Doc 04 §13.2).
    from django.db import connection

    return str(connection.schema_name)  # type: ignore[attr-defined]  # django-tenants


def _audit(
    actor: StaffUser | None,
    action: str,
    settlement: Settlement,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    AuditLog.objects.create(
        actor_id=actor.id if actor is not None else None,
        action=action,
        entity_type="settlement",
        entity_id=settlement.id,
        before_jsonb=before,
        after_jsonb=after,
        ip="",
        user_agent="",
    )


def _delivery_series_key(settlement_id: uuid.UUID | str) -> str:
    """Idempotency key per settlement delivery attempt series (DL-3)."""
    return f"settlement_delivery:{settlement_id}"


def dispatch_settlement_delivery(
    settlement: Settlement,
    *,
    actor: StaffUser | None = None,
    is_resend: bool = False,
) -> Notification:
    """Record the delivery intent for an APPROVED (or SENT, on re-send) settlement.

    - Partner email missing -> FAILED notification with
      last_error='partner_email_missing'; settlement stays APPROVED (ST-21).
    - Otherwise: PENDING notification + PENDING webhook_delivery row, and the
      deliver task is enqueued. SENT is set by callback only (DL-3).
    - Idempotent per attempt series: a second dispatch for the same series
      returns the existing row (DL-3 UNIQUE idempotency_key).
    """
    allowed = {Settlement.Status.APPROVED}
    if is_resend:
        allowed.add(Settlement.Status.SENT)
    if settlement.status not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot dispatch delivery from status {settlement.status}."
        )

    partner = settlement.referral_partner
    email = (partner.email or "").strip()

    series_key = _delivery_series_key(settlement.id)
    if is_resend:
        # DL-6: re-send creates a FRESH notification row — the failed row
        # stays as the record of the failure.
        series_key = f"{series_key}:resend:{uuid.uuid4().hex[:8]}"
    is_copy = is_resend and settlement.status == Settlement.Status.SENT

    with transaction.atomic():
        existing = Notification.objects.filter(idempotency_key=series_key).first()
        if existing is not None and not is_resend:
            return existing

        if not email:
            notif = Notification.objects.create(
                template_key=TEMPLATE_KEY,
                recipient_type=Notification.RecipientType.PARTNER,
                recipient_id=partner.id,
                channel=Notification.Channel.EMAIL,
                status=Notification.Status.FAILED,
                last_error=EMAIL_MISSING_ERROR,
                idempotency_key=series_key,
            )
            _audit(
                actor,
                "settlement.delivery_failed",
                settlement,
                {"status": settlement.status},
                {
                    "status": settlement.status,
                    "last_error": EMAIL_MISSING_ERROR,
                },
            )
            logger.warning(
                "settlement delivery: partner %s has no email; "
                "notification %s FAILED (%s); settlement %s stays %s",
                partner.id,
                notif.id,
                EMAIL_MISSING_ERROR,
                settlement.id,
                settlement.status,
            )
            return notif

        notif = Notification.objects.create(
            template_key=TEMPLATE_KEY,
            recipient_type=Notification.RecipientType.PARTNER,
            recipient_id=partner.id,
            channel=Notification.Channel.EMAIL,
            status=Notification.Status.PENDING,
            idempotency_key=series_key,
        )
        callback_url = _callback_url()
        body = {
            "event": WEBHOOK_EVENT,
            "tenant_slug": _tenant_slug(),
            "callback_url": callback_url,
            "idempotency_key": series_key,
            "timestamp": int(timezone.now().timestamp()),
            "data": {
                "settlement_id": str(settlement.id),
                "partner_id": str(partner.id),
                "partner_email": email,
                "period": settlement.period,
                "total": str(settlement.total),
                "is_copy": is_copy,
            },
        }
        WebhookDelivery.objects.create(
            event=WEBHOOK_EVENT,
            idempotency_key=series_key,
            payload_jsonb={**body, "signature": _sign_payload(body)},
            status=WebhookDelivery.Status.PENDING,
        )
        _audit(
            actor,
            "settlement.delivery_requested",
            settlement,
            {"status": settlement.status},
            {"status": settlement.status, "notification_id": str(notif.id)},
        )

    # Enqueue outside the transaction so a rollback never orphans a task.
    from apps.partners.tasks import deliver_settlement_task

    deliver_settlement_task.delay(_tenant_slug(), str(notif.id))
    return notif


def _callback_url() -> str:
    base = str(getattr(settings, "APP_BASE_URL", "") or "").rstrip("/")
    if base:
        return f"{base}/api/v1/settlements/delivery-callback"
    return "/api/v1/settlements/delivery-callback"


def handle_delivery_callback(
    resolved_tenant_slug: str,
    body: dict[str, Any],
    *,
    signature: str,
) -> dict[str, Any]:
    """Process n8n's delivery callback (DL-2, DL-3).

    Verifies HMAC-SHA256 and that the body's tenant_slug matches the tenant
    resolved from the callback's subdomain. On success the notification row
    becomes SENT and the settlement moves APPROVED -> SENT. SENT is set by
    the callback, never assumed at send time.
    """
    expected = _sign_payload(body)
    if not hmac.compare_digest(expected, signature or ""):
        raise InvalidSignatureError("Callback signature mismatch.")
    if body.get("tenant_slug") != resolved_tenant_slug:
        raise TenantMismatchError("Callback tenant_slug mismatch.")
    try:
        notif = Notification.objects.get(
            idempotency_key=body.get("idempotency_key"),
            template_key=TEMPLATE_KEY,
        )
    except Notification.DoesNotExist as err:
        raise SettlementNotFoundError("Notification row not found.") from err

    with transaction.atomic():
        notif = Notification.objects.select_for_update().get(pk=notif.pk)
        if notif.status == Notification.Status.SENT:
            return {"status": "ok", "duplicate": True}
        notif.status = Notification.Status.SENT
        notif.last_error = None
        notif.save(update_fields=["status", "last_error", "updated_at"])

        WebhookDelivery.objects.filter(idempotency_key=notif.idempotency_key).update(
            status=WebhookDelivery.Status.SENT, updated_at=timezone.now()
        )

        settlement = _settlement_for_notification(notif)
        if settlement is not None and (settlement.status == Settlement.Status.APPROVED):
            before = {"status": settlement.status}
            settlement.status = Settlement.Status.SENT
            settlement.save(update_fields=["status", "updated_at"])
            _audit(
                None,
                "settlement.sent",
                settlement,
                before,
                {"status": settlement.status},
            )
    return {"status": "ok", "duplicate": False}


def _settlement_for_notification(
    notif: Notification,
) -> Settlement | None:
    """Recover the settlement from the webhook payload's data block."""
    hook = (
        WebhookDelivery.objects.filter(idempotency_key=notif.idempotency_key)
        .order_by("-created_at")
        .first()
    )
    if hook is None:
        return None
    settlement_id = (hook.payload_jsonb or {}).get("data", {}).get("settlement_id")
    if not settlement_id:
        return None
    try:
        return Settlement.objects.get(pk=settlement_id)
    except (Settlement.DoesNotExist, ValueError):
        return None


def backoff_for_attempt(attempts: int) -> int:
    """Doc 01 §13 notifications policy: 30 s -> 30 min across 5 attempts."""
    idx = min(max(attempts, 0), len(DELIVERY_BACKOFF_SECONDS) - 1)
    return DELIVERY_BACKOFF_SECONDS[idx]


def record_attempt_failure(notif: Notification, error: str) -> None:
    """Bump attempts/next_attempt_at; exhaust -> FAILED + alert (DL-5)."""
    notif.attempts += 1
    notif.last_error = error[:500]
    if notif.attempts >= DELIVERY_MAX_ATTEMPTS:
        notif.status = Notification.Status.FAILED
        notif.next_attempt_at = None
        notif.save(
            update_fields=[
                "attempts",
                "last_error",
                "status",
                "next_attempt_at",
                "updated_at",
            ]
        )
        # Sentry alert path (Doc 01 §13): exhausted deliveries alert.
        logger.error(
            "settlement delivery exhausted: notification %s (%s) FAILED "
            "after %d attempts; last_error=%s",
            notif.id,
            notif.idempotency_key,
            notif.attempts,
            error,
        )
    else:
        notif.status = Notification.Status.PENDING
        notif.next_attempt_at = timezone.now() + timedelta(
            seconds=backoff_for_attempt(notif.attempts)
        )
        notif.save(
            update_fields=[
                "attempts",
                "last_error",
                "status",
                "next_attempt_at",
                "updated_at",
            ]
        )
