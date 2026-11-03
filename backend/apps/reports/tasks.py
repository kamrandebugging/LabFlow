"""Celery tasks for the Reports app (KAN-155 / LAB-30, original LAB-35).

reports.generate_pdf (reports queue, Doc 01 §13):
- Renders one report version with WeasyPrint (LAB-29) and uploads the PDF to
  object storage at the deterministic key reports/{report_id}/{version}.pdf.
- Upload-then-insert (§10): no report_version row is written until the PDF
  bytes exist and the upload is confirmed. A render/storage exception fails
  the task cleanly — the report keeps its previous state and
  generation_status=failed with the error text (visible failure, §10).
- Idempotent: the target version is derived as current_version + 1 and the
  (report, version) row is checked under lock — a repeat run that finds the
  row exits as success without re-rendering.
- RP-3: content is frozen at generation time from the approved results and
  their selected ranges (P-8); later catalog edits never change a version.
- Retry policy (5 retries, backoff 10s–5min, Doc 01 §13) is a worker-level
  concern; the task marks the failure visibly and re-raises so the broker
  policy applies.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog, TenantSetting
from apps.notifications.models import NotificationTemplate
from apps.reports.models import Report, ReportDelivery, ReportVersion
from apps.reports.pdf.builder import build_report_context
from apps.reports.pdf.rendering import render_report_pdf
from apps.reports.services import _mint_access_token_core
from apps.reports.storage import ReportStorage

logger = logging.getLogger(__name__)

TASK_NAME = "reports.generate_pdf"
DELIVER_TASK_NAME = "reports.deliver"
RETRY_SWEEP_TASK_NAME = "reports.retry_failed_deliveries"
# Doc 03 §6.7 RP-6: seeded notification template for the delivery message.
DELIVERY_TEMPLATE_KEY = "report_ready"
# Doc 04 §10.2: tenant default language for delivery messages (LAB-22 pattern).
DELIVERY_LANGUAGE_SETTING = "report_default_language"
# v1 retry policy: row-level (FAILED + next_attempt_at), driven by the
# 15-minute beat sweep. After this many attempts the row is parked
# (next_attempt_at=None) for manual handling.
MAX_DELIVERY_ATTEMPTS = 5
# Beat claim lease: the sweep pushes next_attempt_at out by this much when
# it re-enqueues a row, so overlapping beat runs cannot double-enqueue.
SWEEP_CLAIM_LEASE = timedelta(minutes=30)
SWEEP_BATCH_LIMIT = 100


def _log_metric(name: str, **fields: Any) -> None:
    """Structured operational metric.

    Emitted as log fields on the apps.reports.tasks logger (stdout in every
    deployment; the log aggregator — Loki/CloudWatch per environment —
    is the v1 metrics backend). There is deliberately no metrics table in
    v1; Prometheus/OpenTelemetry export is a later observability LAB.
    """
    logger.info("metric %s", name, extra={"metric": name, **fields})


def _pdf_key(report_id: uuid.UUID, version: int) -> str:
    return f"reports/{report_id}/{version}.pdf"


@shared_task(name=TASK_NAME)
def generate_pdf_task(
    schema_name: str,
    report_id: str,
    triggered_by: str | None,
    target_version: int,
) -> dict[str, Any]:
    """Generate one report PDF version asynchronously.

    triggered_by: the StaffUser id that requested the generation (manual
    regenerate), or None for automatic triggers (sample ready, amendment).
    target_version: the exact version to generate (computed by the caller at
    enqueue time as current_version + 1). Idempotency is per (report,
    target_version): a repeat run that finds the row exits as success.
    """
    with schema_context(schema_name):
        try:
            report_uuid = uuid.UUID(report_id)
        except (ValueError, TypeError):
            logger.warning("reports.generate_pdf: bad report id %r — skip", report_id)
            return {"status": "skipped", "reason": "bad_report_id"}
        if not isinstance(target_version, int) or target_version < 1:
            logger.warning(
                "reports.generate_pdf: bad target version %r — skip", target_version
            )
            return {"status": "skipped", "reason": "bad_target_version"}

        # Operational metric (LAB-32): task duration + failure counts go to
        # the structured log via _log_metric (see its docstring for where).
        started = time.monotonic()

        with transaction.atomic():
            try:
                report = Report.objects.select_for_update().get(pk=report_uuid)
            except Report.DoesNotExist:
                logger.warning(
                    "reports.generate_pdf: report %s not found in schema %s — skip",
                    report_id,
                    schema_name,
                )
                return {"status": "skipped", "reason": "report_not_found"}
            if report.status == Report.Status.VOID:
                logger.info("reports.generate_pdf: report %s is void — skip", report_id)
                return {"status": "skipped", "reason": "report_void"}

            next_version = target_version
            pdf_key = _pdf_key(report.id, next_version)

            # Idempotency: the target version row already exists -> success.
            if ReportVersion.objects.filter(
                report=report, version=next_version
            ).exists():
                if report.generation_status != Report.GenerationStatus.IDLE:
                    report.generation_status = Report.GenerationStatus.IDLE
                    report.generation_error = None
                    report.save(
                        update_fields=[
                            "generation_status",
                            "generation_error",
                            "updated_at",
                        ]
                    )
                logger.info(
                    "reports.generate_pdf: version %d of report %s already "
                    "exists — deduplicated",
                    next_version,
                    report_id,
                )
                return {
                    "status": "ok",
                    "report_id": str(report.id),
                    "version": next_version,
                    "pdf_key": pdf_key,
                    "deduplicated": True,
                }

            report.generation_status = Report.GenerationStatus.RUNNING
            report.generation_error = None
            report.save(
                update_fields=["generation_status", "generation_error", "updated_at"]
            )

        # Render + upload OUTSIDE the row lock (WeasyPrint can take seconds;
        # the in-flight guard is generation_status=running). Any exception ->
        # visible failure, no partial version row (§10).
        finalised_at = timezone.now()
        try:
            ctx = build_report_context(report, next_version, finalised_at=finalised_at)
            pdf_bytes = render_report_pdf(ctx)
            ReportStorage().save_pdf(pdf_key, pdf_bytes)
        except Exception as exc:
            logger.exception(
                "reports.generate_pdf: generation failed for report %s v%d",
                report_id,
                next_version,
            )
            _log_metric(
                "generate_pdf.failure",
                task=TASK_NAME,
                report_id=report_id,
                version=next_version,
                error=type(exc).__name__,
            )
            with transaction.atomic():
                locked = Report.objects.select_for_update().get(pk=report.pk)
                locked.generation_status = Report.GenerationStatus.FAILED
                locked.generation_error = f"{type(exc).__name__}: {exc}"[:2000]
                locked.save(
                    update_fields=[
                        "generation_status",
                        "generation_error",
                        "updated_at",
                    ]
                )
            raise

        # Upload-then-insert: the version row lands only after the PDF exists.
        with transaction.atomic():
            locked = Report.objects.select_for_update().get(pk=report.pk)
            version_row, created = ReportVersion.objects.get_or_create(
                report=locked,
                version=next_version,
                defaults={
                    "pdf_key": pdf_key,
                    "generated_by_id": uuid.UUID(triggered_by)
                    if triggered_by
                    else None,
                },
            )
            if not created:
                # Lost a race with another worker — treat as success.
                logger.info(
                    "reports.generate_pdf: version %d of report %s raced — "
                    "deduplicated",
                    next_version,
                    report_id,
                )
                return {
                    "status": "ok",
                    "report_id": str(report.id),
                    "version": next_version,
                    "pdf_key": pdf_key,
                    "deduplicated": True,
                }
            locked.current_version = next_version
            locked.status = (
                Report.Status.FINAL if next_version == 1 else Report.Status.AMENDED
            )
            locked.finalised_at = finalised_at
            locked.generation_status = Report.GenerationStatus.IDLE
            locked.generation_error = None
            locked.save(
                update_fields=[
                    "current_version",
                    "status",
                    "finalised_at",
                    "generation_status",
                    "generation_error",
                    "updated_at",
                ]
            )
            AuditLog.objects.create(
                actor_id=uuid.UUID(triggered_by) if triggered_by else None,
                action="report.version_generated",
                entity_type="report",
                entity_id=locked.id,
                before_jsonb={
                    "previous_version": next_version - 1,
                    "previous_status": report.status,
                },
                after_jsonb={
                    "version": next_version,
                    "status": locked.status,
                    "pdf_key": pdf_key,
                    "event": "report.version_generated",
                },
            )
        logger.info(
            "reports.generate_pdf: report %s v%d generated (%d bytes)",
            report_id,
            next_version,
            len(pdf_bytes),
        )
        _log_metric(
            "generate_pdf.duration",
            task=TASK_NAME,
            report_id=report_id,
            version=next_version,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return {
            "status": "ok",
            "report_id": str(report.id),
            "version": next_version,
            "pdf_key": pdf_key,
        }


# ---------------------------------------------------------------------------
# reports.deliver (KAN-157 / LAB-32, original LAB-37)
# ---------------------------------------------------------------------------


def _tenant_setting(key: str, default: str) -> str:
    row = TenantSetting.objects.filter(key=key).first()
    return row.value if row is not None else default


def _render_template_body(body: str, context: dict[str, str]) -> str:
    """Minimal v1 {{ var }} renderer (spaced and unspaced forms).

    A full template engine for notification bodies arrives with the Doc 06
    delivery provider; v1 only substitutes the documented context variables.
    Unknown placeholders are left untouched (visible, not silent).
    """
    for key, value in context.items():
        body = body.replace("{{ " + key + " }}", value)
        body = body.replace("{{" + key + "}}", value)
    return body


def _fallback_delivery_message(
    locale: str, *, patient_name: str, accession_id: str, patient_link: str
) -> str:
    """Interim message when the report_ready template is not seeded
    (LAB-22 fallback pattern). Plain, short, no result values."""
    if locale == "ur":
        return (
            f"محترم {patient_name}، آپ کی رپورٹ ({accession_id}) "
            f"تیار ہے: {patient_link}"
        )
    return f"Dear {patient_name}, your report ({accession_id}) is ready: {patient_link}"


def _patient_link_base(schema_name: str) -> tuple[str, str]:
    """(absolute base URL, lab name) for patient links.

    Resolved from the tenant's primary Domain row (public schema — the
    core app is shared, so this works inside schema_context). Falls back
    to ("", "") — a relative link — when no domain row exists; production
    tenants always have one because provisioning creates it.
    """
    # Local import: apps.core lives in the public schema; importing it here
    # keeps the module import graph flat.
    from apps.core.models import Domain

    domain = (
        Domain.objects.filter(tenant__schema_name=schema_name, is_primary=True)
        .select_related("tenant")
        .order_by("domain")
        .first()
    )
    if domain is None:
        return "", ""
    return f"https://{domain.domain}", domain.tenant.name


def _delivery_backoff(attempts: int) -> timedelta:
    """Row-level retry backoff: 5m, 10m, 20m, 40m, capped at 60m."""
    return timedelta(seconds=min(300 * (2 ** max(attempts - 1, 0)), 3600))


def _build_delivery_message(
    schema_name: str, delivery: ReportDelivery
) -> tuple[str, str | None, str, str]:
    """Build (message, whatsapp_url, token_id, template_name) for a delivery.

    Re-mints a fresh access token at SEND time via the shared LAB-31 mint:
    the plain token lives only in this worker's memory and inside the
    message — it never crosses the broker and never touches the DB, logs
    or audit. A queued-then-retried delivery therefore always embeds a
    link with a fresh validity window.
    """
    from django.urls import reverse

    report = delivery.report
    sample = report.sample
    patient = sample.invoice.patient
    contact = delivery.contact

    locale = _tenant_setting(DELIVERY_LANGUAGE_SETTING, "en")
    if locale not in ("en", "ur"):
        locale = "en"
    template = NotificationTemplate.objects.filter(
        key=DELIVERY_TEMPLATE_KEY,
        locale=locale,
        channel=delivery.channel,
    ).first()

    token_row, plain = _mint_access_token_core(report)
    base, lab_name = _patient_link_base(schema_name)
    path = reverse("report-access", kwargs={"token": plain})
    patient_link = f"{base}{path}" if base else path

    branch = sample.branch
    context = {
        "patient_name": patient.name,
        "accession_id": sample.accession_id,
        "patient_link": patient_link,
        "lab_name": lab_name or (branch.name if branch else "the laboratory"),
    }
    if template is None:
        logger.info(
            "reports.deliver: template '%s' (%s/%s) not seeded — "
            "using interim fallback message.",
            DELIVERY_TEMPLATE_KEY,
            locale,
            delivery.channel,
        )
        message = _fallback_delivery_message(
            locale,
            patient_name=context["patient_name"],
            accession_id=context["accession_id"],
            patient_link=patient_link,
        )
        template_name = "fallback"
    else:
        message = _render_template_body(template.body, context)
        template_name = DELIVERY_TEMPLATE_KEY

    whatsapp_url: str | None = None
    if delivery.channel == ReportDelivery.Channel.WHATSAPP:
        # Doc 02 §5.7: whatsapp_url is the click-to-send URL. v1 has no
        # provider callback, so the worker builds it (staff taps it to
        # open the chat with the message pre-filled).
        digits = re.sub(r"\D", "", contact.value or "")
        if not digits:
            raise ValueError("Contact has no usable phone number.")
        # NOTE: numbers are used as stored; E.164 normalization of local
        # Pakistani formats (0300…) is deferred to the Doc 06 provider.
        whatsapp_url = f"https://wa.me/{digits}?text={quote(message)}"
    return message, whatsapp_url, str(token_row.id), template_name


@shared_task(name=DELIVER_TASK_NAME, queue="notifications", max_retries=0)
def deliver_report_task(schema_name: str, delivery_id: str) -> dict[str, Any]:
    """Dispatch one report delivery (Doc 03 §5.6 RP-6, §10; KAN-157/LAB-32).

    Idempotent: the delivery row is claimed with SELECT FOR UPDATE and a
    row already SENT (or OPENED by the patient) is never re-sent — the
    §10 pattern from samples.notify_rejection. The whole claim -> build ->
    flip runs in one transaction, so two workers racing on one row
    serialize on the lock and the loser sees the terminal state.

    v1 records the delivery INTENT: there is no real SMS/WhatsApp/email
    provider, so success means the hand-off artefacts (message body +
    whatsapp_url click-to-send URL for WhatsApp) are built and stored and
    the row flips to SENT — exactly like notify_rejection records PENDING
    intents without sending. A Doc 06 provider plugs into
    _build_delivery_message later.

    Retry is row-level, not Celery-level (max_retries=0): on failure the
    row goes FAILED with attempts+1 and next_attempt_at = now + backoff;
    the 15-minute beat sweep re-enqueues it. After MAX_DELIVERY_ATTEMPTS
    the row is parked (next_attempt_at=None) for manual handling.
    """
    with schema_context(schema_name):
        try:
            delivery_pk = uuid.UUID(delivery_id)
        except (ValueError, TypeError):
            logger.warning("reports.deliver: bad delivery id %r — skip", delivery_id)
            return {"status": "skipped", "reason": "bad_delivery_id"}

        with transaction.atomic():
            try:
                delivery = (
                    ReportDelivery.objects.select_for_update()
                    .select_related(
                        "report__sample__invoice__patient",
                        "report__sample__branch",
                        "contact",
                    )
                    .get(pk=delivery_pk)
                )
            except ReportDelivery.DoesNotExist:
                logger.warning(
                    "reports.deliver: delivery %s not found in schema %s — skip",
                    delivery_id,
                    schema_name,
                )
                return {"status": "skipped", "reason": "delivery_not_found"}
            if delivery.status in (
                ReportDelivery.Status.SENT,
                ReportDelivery.Status.OPENED,
            ):
                return {"status": "skipped", "reason": "already_sent"}
            if delivery.status == ReportDelivery.Status.BOUNCED:
                return {"status": "skipped", "reason": "bounced"}
            if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
                # Parked for manual handling: make it explicit in the row
                # (the sweep skips attempts >= MAX, so nothing else will).
                if delivery.next_attempt_at is not None:
                    delivery.next_attempt_at = None
                    delivery.save(update_fields=["next_attempt_at", "updated_at"])
                return {"status": "skipped", "reason": "attempts_exhausted"}

            now = timezone.now()
            try:
                _message, whatsapp_url, token_id, template_name = (
                    _build_delivery_message(schema_name, delivery)
                )
            except Exception as exc:
                logger.exception(
                    "reports.deliver: delivery %s failed (attempt %d)",
                    delivery_id,
                    delivery.attempts + 1,
                )
                delivery.attempts += 1
                if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
                    # Parked for manual handling — the sweep skips these.
                    delivery.next_attempt_at = None
                else:
                    delivery.next_attempt_at = now + _delivery_backoff(
                        delivery.attempts
                    )
                delivery.status = ReportDelivery.Status.FAILED
                delivery.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                delivery.save(
                    update_fields=[
                        "attempts",
                        "next_attempt_at",
                        "status",
                        "last_error",
                        "updated_at",
                    ]
                )
                AuditLog.objects.create(
                    actor_id=None,
                    action="report.delivery_failed",
                    entity_type="report_delivery",
                    entity_id=delivery.id,
                    after_jsonb={
                        "delivery_id": str(delivery.id),
                        "channel": delivery.channel,
                        "attempts": delivery.attempts,
                        "error": delivery.last_error,
                        "event": "report.delivery_failed",
                    },
                )
                _log_metric(
                    "delivery.attempt",
                    task=DELIVER_TASK_NAME,
                    delivery_id=str(delivery.id),
                    channel=delivery.channel,
                    status="failed",
                    attempts=delivery.attempts,
                )
                return {
                    "status": "failed",
                    "delivery_id": str(delivery.id),
                    "attempts": delivery.attempts,
                }

            delivery.status = ReportDelivery.Status.SENT
            delivery.sent_at = now
            delivery.whatsapp_url = whatsapp_url
            delivery.save(
                update_fields=["status", "sent_at", "whatsapp_url", "updated_at"]
            )
            AuditLog.objects.create(
                actor_id=None,
                action="report.delivery_sent",
                entity_type="report_delivery",
                entity_id=delivery.id,
                after_jsonb={
                    "delivery_id": str(delivery.id),
                    "report_id": str(delivery.report_id),
                    "channel": delivery.channel,
                    "contact_id": str(delivery.contact_id),
                    "token_id": token_id,
                    "template": template_name,
                    "event": "report.delivery_sent",
                },
            )
            _log_metric(
                "delivery.attempt",
                task=DELIVER_TASK_NAME,
                delivery_id=str(delivery.id),
                channel=delivery.channel,
                status="sent",
                attempts=delivery.attempts,
                latency_ms=int(
                    (delivery.sent_at - delivery.created_at).total_seconds() * 1000
                ),
            )
            logger.info(
                "reports.deliver: delivery %s sent via %s",
                delivery_id,
                delivery.channel,
            )
            return {
                "status": "ok",
                "delivery_id": str(delivery.id),
                "channel": delivery.channel,
                "template": template_name,
            }


@shared_task(name=RETRY_SWEEP_TASK_NAME)
def retry_failed_deliveries_task() -> dict[str, Any]:
    """Beat every 15 min (Doc 02 §5.7): re-enqueue FAILED deliveries with
    next_attempt_at <= now and attempts < MAX_DELIVERY_ATTEMPTS.

    TP-5 fan-out across tenant schemas (same pattern as
    accounts.cleanup_expired_tokens).

    Claim race (§10): each due row is claimed with SELECT FOR UPDATE ...
    SKIP LOCKED and its next_attempt_at is pushed out by SWEEP_CLAIM_LEASE
    BEFORE the task is enqueued, so two overlapping beat runs cannot
    double-enqueue a row. If the worker then crashes, the lease expiry
    makes the row due again. The deliver task's locked status check is the
    second backstop: a SENT row is never re-sent even if enqueued twice.
    """
    # Local import: the core app lives in the public schema.
    from apps.core.models import Tenant

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
                        ReportDelivery.objects.select_for_update(skip_locked=True)
                        .filter(
                            status=ReportDelivery.Status.FAILED,
                            next_attempt_at__lte=now,
                            attempts__lt=MAX_DELIVERY_ATTEMPTS,
                        )
                        .order_by("next_attempt_at")[:SWEEP_BATCH_LIMIT]
                    )
                    due_ids: list[str] = []
                    for delivery in due:
                        delivery.next_attempt_at = now + SWEEP_CLAIM_LEASE
                        delivery.save(update_fields=["next_attempt_at", "updated_at"])
                        due_ids.append(str(delivery.id))
                for delivery_id in due_ids:
                    deliver_report_task.delay(schema_name, delivery_id)
                requeued += len(due_ids)
                per_tenant[schema_name] = len(due_ids)
                if due_ids:
                    logger.info(
                        "reports.retry_failed_deliveries: requeued %d in %s",
                        len(due_ids),
                        schema_name,
                    )
        except Exception:
            logger.exception(
                "reports.retry_failed_deliveries: failed for schema %s", schema_name
            )
    return {"status": "ok", "requeued": requeued, "tenants": per_tenant}
