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
import uuid
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog
from apps.reports.models import Report, ReportVersion
from apps.reports.pdf.builder import build_report_context
from apps.reports.pdf.rendering import render_report_pdf
from apps.reports.storage import ReportStorage

logger = logging.getLogger(__name__)

TASK_NAME = "reports.generate_pdf"


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
        return {
            "status": "ok",
            "report_id": str(report.id),
            "version": next_version,
            "pdf_key": pdf_key,
        }
