"""Celery tasks for monthly settlement generation (LAB-41 / KAN-260).

Doc 05 §7.2 (ST-1, ST-2): Beat fires
`referral_partners.generate_monthly_settlements` on the 1st at 01:00
Asia/Karachi. Fan-out: parent -> one task per tenant -> one draft task
per partner with pending entries. One tenant's failure cannot abort the
rest; one partner's failure cannot abort the tenant's other partners.

Doc 05 §7.4 (ST-10, ST-11): `referral_partners.finalize_settlement`
renders the PDF, uploads it, sets statement_pdf_key, then fires the
delivery webhook (PDF-first ordering).
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

PARENT_TASK_NAME = "referral_partners.generate_monthly_settlements"
TENANT_TASK_NAME = "referral_partners.generate_tenant_settlements"
DRAFT_TASK_NAME = "referral_partners.generate_partner_draft"
FINALIZE_TASK_NAME = "referral_partners.finalize_settlement"

# Object-storage key pattern (Doc 05 §7.4 ST-11).
STATEMENT_KEY_TEMPLATE = "settlements/{partner_id}/{period}.pdf"


def _statement_key(partner_id: uuid.UUID, period: str) -> str:
    return STATEMENT_KEY_TEMPLATE.format(partner_id=partner_id, period=period)


@shared_task(name=PARENT_TASK_NAME, bind=True, max_retries=0)
def generate_monthly_settlements(self: Any) -> dict[str, Any]:
    """Beat entry point: fan out one child task per tenant (Doc 05 ST-2).

    Beat is a single scheduler; it never loops over tenant schemas here —
    each child task runs inside its own tenant's schema.
    """
    # Import here to avoid app-loading issues at module import time.
    from django.apps import apps as django_apps

    tenant_model = django_apps.get_model("core", "Tenant")
    tenants = list(
        tenant_model.objects.exclude(schema_name="public").values_list(
            "schema_name", flat=True
        )
    )
    enqueued = 0
    for schema_name in tenants:
        generate_tenant_settlements.delay(schema_name)
        enqueued += 1
    logger.info("settlement generation: parent fanned out to %d tenants", enqueued)
    return {"status": "fanned_out", "tenants": enqueued}


@shared_task(name=TENANT_TASK_NAME, bind=True, max_retries=3, default_retry_delay=60)
def generate_tenant_settlements(self: Any, schema_name: str) -> dict[str, Any]:
    """Per-tenant generation: fan out one draft task per partner (Doc 05 ST-2)."""
    from apps.partners.models import ReferralPartner
    from apps.partners.settlement_service import (
        _pending_entry_ids,
        previous_period,
    )

    period = previous_period()
    drafted = 0
    skipped = 0
    failed = 0
    with schema_context(schema_name):
        partners = list(ReferralPartner.objects.all().values_list("id", flat=True))
        for partner_id in partners:
            try:
                if not _pending_entry_ids(partner_id):
                    skipped += 1
                    continue
                generate_partner_draft.delay(schema_name, str(partner_id), period)
                drafted += 1
            except Exception:
                logger.exception(
                    "settlement generation: enqueue failed for partner %s",
                    partner_id,
                )
                failed += 1
    _log_metric(
        "settlement_generation_tenant",
        schema=schema_name,
        period=period,
        drafted=drafted,
        skipped=skipped,
        failed=failed,
    )
    if drafted > 0:
        # ST-8: notify the Owner once per tenant when drafting completes.
        _notify_owner_drafts_ready(schema_name, period)
    return {
        "status": "ok",
        "schema": schema_name,
        "period": period,
        "drafted": drafted,
        "skipped": skipped,
        "failed": failed,
    }


@shared_task(name=DRAFT_TASK_NAME, bind=True, max_retries=3, default_retry_delay=60)
def generate_partner_draft(
    self: Any, schema_name: str, partner_id: str, period: str
) -> dict[str, Any]:
    """Draft one partner's settlement (Doc 05 §7.2 ST-4–ST-7)."""
    from apps.partners.settlement_service import draft_partner_settlement

    with schema_context(schema_name):
        try:
            partner_uuid = uuid.UUID(partner_id)
        except (ValueError, TypeError):
            logger.warning("settlement draft: bad partner id %r — skip", partner_id)
            return {"status": "skipped", "reason": "bad_partner_id"}
        result = draft_partner_settlement(partner_uuid, period)
        return result


def _notify_owner_drafts_ready(schema_name: str, period: str) -> None:
    """Notify the Owner that drafts are ready for review (Doc 05 ST-8)."""
    from apps.notifications.models import Notification

    Notification.objects.create(
        template_key="settlement_drafts_ready",
        recipient_type=Notification.RecipientType.STAFF,
        channel=Notification.Channel.EMAIL,
        status=Notification.Status.PENDING,
        idempotency_key=f"settlement-drafts-ready-{schema_name}-{period}",
    )


@shared_task(name=FINALIZE_TASK_NAME, bind=True, max_retries=3, default_retry_delay=120)
def finalize_settlement(
    self: Any, schema_name: str, settlement_id: str
) -> dict[str, Any]:
    """Finalize an approved settlement (Doc 05 §7.4 ST-11).

    Render -> upload -> set statement_pdf_key -> fire webhook (PDF first).
    A render exception fails the task cleanly; no partial PDF is kept
    (Doc 05 PDF-3). A crash between storing the PDF and firing the webhook
    leaves APPROVED with statement_pdf_key set and no notification row —
    a re-run detects that exact state and fires the webhook (§12.7).
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from apps.notifications.models import Notification
    from apps.partners.models import Settlement
    from apps.partners.settlement_service import (
        STATEMENT_TEMPLATE_VERSION,
        build_statement_context,
    )
    from apps.partners.statement_pdf import render_statement_pdf

    with schema_context(schema_name):
        try:
            settlement_uuid = uuid.UUID(settlement_id)
        except (ValueError, TypeError):
            logger.warning("finalize: bad settlement id %r — skip", settlement_id)
            return {"status": "skipped", "reason": "bad_settlement_id"}

        try:
            settlement = Settlement.objects.select_related("referral_partner").get(
                id=settlement_uuid
            )
        except Settlement.DoesNotExist:
            logger.warning("finalize: settlement %s not found — skip", settlement_id)
            return {"status": "skipped", "reason": "not_found"}

        if settlement.status != Settlement.Status.APPROVED:
            logger.warning(
                "finalize: settlement %s is %s, not APPROVED — skip",
                settlement_id,
                settlement.status,
            )
            return {"status": "skipped", "reason": "not_approved"}

        key = _statement_key(settlement.referral_partner_id, settlement.period)

        # PDF-first ordering (ST-11): render and upload before any webhook.
        if not settlement.statement_pdf_key:
            ctx = build_statement_context(settlement.id)
            pdf_bytes = render_statement_pdf(ctx)  # raises cleanly on failure
            default_storage.save(key, ContentFile(pdf_bytes))
            settlement.statement_pdf_key = key
            settlement.save(update_fields=["statement_pdf_key", "updated_at"])
            logger.info("finalize: PDF stored at %s", key)

        # Crash recovery (§12.7): if the webhook was never fired, fire it now.
        webhook_key = f"settlement-approved-{settlement.id}"
        already = Notification.objects.filter(idempotency_key=webhook_key).exists()
        if not already:
            _fire_settlement_webhook(settlement, webhook_key)

        return {
            "status": "finalized",
            "settlement_id": str(settlement.id),
            "pdf_key": settlement.statement_pdf_key,
            "template_version": STATEMENT_TEMPLATE_VERSION,
        }


def _fire_settlement_webhook(settlement: Any, idempotency_key: str) -> None:
    """Fire the 'settlement approved' delivery webhook (Doc 05 §9).

    Only after the PDF exists (ST-11). A webhook never points at a PDF
    that does not exist.
    """
    from apps.notifications.models import Notification

    Notification.objects.create(
        template_key="settlement_approved",
        recipient_type=Notification.RecipientType.PARTNER,
        recipient_id=settlement.referral_partner_id,
        channel=Notification.Channel.EMAIL,
        status=Notification.Status.PENDING,
        idempotency_key=idempotency_key,
    )
    logger.info("finalize: webhook queued for settlement %s", settlement.id)


def _log_metric(name: str, **fields: Any) -> None:
    logger.info("metric %s", name, extra={"metric": name, **fields})


DELIVER_TASK_NAME = "partners.deliver_settlement"
RETRY_SWEEP_TASK_NAME = "partners.retry_failed_settlement_deliveries"


def _n8n_webhook_url() -> str:
    return str(getattr(settings, "N8N_WEBHOOK_URL", "") or "")


def _post_to_n8n(url: str, body: dict[str, Any], signature: str) -> None:
    """POST the signed event to n8n. Raises on transport/HTTP failure."""
    resp = requests.post(
        url,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-LabFlow-Signature": signature,
        },
        timeout=30,
    )
    resp.raise_for_status()


@shared_task(name=DELIVER_TASK_NAME, bind=True, max_retries=0)
def deliver_settlement_task(
    self: Any, schema_name: str, notification_id: str
) -> dict[str, Any]:
    """Hand one settlement_ready notification to n8n (DL-2, DL-3)."""
    from apps.automation.models import WebhookDelivery
    from apps.notifications.models import Notification
    from apps.partners.delivery import (
        _sign_payload,
        handle_delivery_callback,
        record_attempt_failure,
    )

    with schema_context(schema_name):
        with transaction.atomic():
            try:
                notif = Notification.objects.select_for_update().get(
                    pk=notification_id, template_key="settlement_ready"
                )
            except (Notification.DoesNotExist, ValueError):
                logger.warning(
                    "partners.deliver_settlement: notification %s not found in "
                    "schema %s — skip",
                    notification_id,
                    schema_name,
                )
                return {"status": "skipped", "reason": "notification_not_found"}

            if notif.status == Notification.Status.SENT:
                # Second backstop against double-send (§10 claim pattern).
                return {"status": "skipped", "reason": "already_sent"}
            if notif.status == Notification.Status.FAILED and (
                notif.last_error == "partner_email_missing"
            ):
                # ST-21: nothing to retry — no inbox exists.
                return {"status": "skipped", "reason": "partner_email_missing"}

        hook = (
            WebhookDelivery.objects.filter(idempotency_key=notif.idempotency_key)
            .order_by("-created_at")
            .first()
        )
        if hook is None:
            logger.error(
                "partners.deliver_settlement: no webhook row for "
                "notification %s — marking FAILED",
                notif.id,
            )
            record_attempt_failure(notif, "webhook_row_missing")
            return {"status": "failed", "reason": "webhook_row_missing"}

        body = dict(hook.payload_jsonb or {})
        signature = str(body.pop("signature", ""))
        if not signature:
            signature = _sign_payload(body)

        # Stub mode (tests / LAB-65 rehearsal): complete via callback path.
        if getattr(settings, "SETTLEMENT_DELIVERY_STUB", False):
            result = handle_delivery_callback(schema_name, body, signature=signature)
            with transaction.atomic():
                hook.status = WebhookDelivery.Status.SENT
                hook.save(update_fields=["status", "updated_at"])
            return {"status": "ok", "stub": True, **result}

        url = _n8n_webhook_url()
        if not url:
            logger.warning(
                "partners.deliver_settlement: N8N_WEBHOOK_URL not "
                "configured — leaving notification %s PENDING",
                notif.id,
            )
            return {"status": "skipped", "reason": "n8n_not_configured"}

        try:
            _post_to_n8n(url, body, signature)
        except Exception as exc:  # noqa: BLE001 — transport failure -> retry
            record_attempt_failure(notif, f"{type(exc).__name__}: {exc}")
            with transaction.atomic():
                hook.status = WebhookDelivery.Status.FAILED
                hook.last_error = str(exc)[:500]
                hook.save(update_fields=["status", "last_error", "updated_at"])
            return {"status": "failed", "reason": "n8n_post_failed"}

        # Handed to n8n; SENT arrives via the callback (DL-3).
        with transaction.atomic():
            notif.attempts += 1
            notif.save(update_fields=["attempts", "updated_at"])
        return {"status": "ok", "handed_to_n8n": True}


@shared_task(name=RETRY_SWEEP_TASK_NAME)
def retry_failed_settlement_deliveries() -> dict[str, Any]:
    """Beat every 15 min (DL-5): re-enqueue due FAILED settlement_ready rows.

    TP-5 fan-out across tenant schemas. Each due row is claimed with
    SELECT FOR UPDATE ... SKIP LOCKED and its next_attempt_at pushed out by
    the claim lease BEFORE the task is enqueued, so two overlapping beat
    runs cannot double-enqueue a row.
    """
    from apps.core.models import Tenant
    from apps.notifications.models import Notification
    from apps.partners.delivery import (
        DELIVERY_MAX_ATTEMPTS,
        SWEEP_BATCH_LIMIT,
        SWEEP_CLAIM_LEASE_SECONDS,
        TEMPLATE_KEY,
    )

    now = timezone.now()
    requeued = 0
    per_tenant: dict[str, int] = {}
    tenants = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
    for tenant in tenants:
        schema_name = tenant.schema_name
        try:
            with schema_context(schema_name):
                with transaction.atomic():
                    due = list(
                        Notification.objects.select_for_update(skip_locked=True)
                        .filter(
                            template_key=TEMPLATE_KEY,
                            status=Notification.Status.FAILED,
                            next_attempt_at__lte=now,
                            attempts__lt=DELIVERY_MAX_ATTEMPTS,
                        )
                        .exclude(last_error="partner_email_missing")
                        .order_by("next_attempt_at")[:SWEEP_BATCH_LIMIT]
                    )
                    due_ids: list[str] = []
                    for notif in due:
                        notif.status = Notification.Status.PENDING
                        notif.next_attempt_at = now + timedelta(
                            seconds=SWEEP_CLAIM_LEASE_SECONDS
                        )
                        notif.save(
                            update_fields=[
                                "status",
                                "next_attempt_at",
                                "updated_at",
                            ]
                        )
                        due_ids.append(str(notif.id))
                for notification_id in due_ids:
                    deliver_settlement_task.delay(schema_name, notification_id)
                requeued += len(due_ids)
                per_tenant[schema_name] = len(due_ids)
                if due_ids:
                    logger.info(
                        "partners.retry_failed_settlement_deliveries: "
                        "requeued %d in %s",
                        len(due_ids),
                        schema_name,
                    )
        except Exception:
            logger.exception(
                "partners.retry_failed_settlement_deliveries: failed for schema %s",
                schema_name,
            )
    return {"status": "ok", "requeued": requeued, "tenants": per_tenant}
