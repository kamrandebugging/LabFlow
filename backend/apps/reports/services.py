"""Report service — async PDF pipeline orchestration (KAN-155 / LAB-30).

Doc 03 §5.6 (RP-1, RP-2, RP-3), §6.7, §10. Thin orchestration only: the actual
rendering lives in apps/reports/pdf/, the Celery task in apps/reports/tasks.py.

Concurrency model (§10):
- reports.generate_pdf is idempotent: deterministic pdf_key
  (reports/{report_id}/{version}.pdf) + existence check for the target
  version — a repeat run that finds the version row exits as success.
- In-flight guard: Report.generation_status (idle|running|failed). The
  request-side claim (SELECT ... FOR UPDATE inside a transaction) runs BEFORE
  enqueueing, so a second enqueue while one is in flight -> 409
  generation_already_running. The worker re-checks under its own lock.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import connection, transaction

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.reports.models import Report

# Doc 03 §6.7: POST /api/v1/reports/{id}/regenerate — roles cell "O M P".
REPORT_REGENERATE_ROLES = {Role.OWNER, Role.MANAGER, Role.PATHOLOGIST}


class ReportError(Exception):
    error_code = "report_error"
    status_code = 400

    def __init__(self, message: str = "", details: Any = None) -> None:
        super().__init__(message)
        self.details = details


class ReportNotFoundError(ReportError):
    error_code = "not_found"
    status_code = 404


class ReportVoidError(ReportError):
    error_code = "report_void"
    status_code = 409


class GenerationAlreadyRunningError(ReportError):
    error_code = "generation_already_running"
    status_code = 409


def _schema_name() -> str:
    tenant = getattr(connection, "tenant", None)
    return getattr(tenant, "schema_name", "public")


def _enqueue_generate_pdf(
    report_id: uuid.UUID, triggered_by: uuid.UUID | None, target_version: int
) -> None:
    """Enqueue reports.generate_pdf AFTER the caller's transaction commits."""
    schema_name = _schema_name()
    report_pk = str(report_id)
    actor_pk = str(triggered_by) if triggered_by is not None else None

    def _enqueue() -> None:
        from apps.reports.tasks import generate_pdf_task

        generate_pdf_task.delay(schema_name, report_pk, actor_pk, target_version)

    transaction.on_commit(_enqueue)


class ReportService:
    """Orchestration for the async report PDF pipeline."""

    @staticmethod
    def _get_report(report_id: uuid.UUID) -> Report:
        try:
            return Report.objects.get(pk=report_id)
        except (Report.DoesNotExist, ValueError, TypeError) as exc:
            raise ReportNotFoundError("Report not found.") from exc

    @staticmethod
    def _claim_generation(report: Report) -> Report | None:
        """Atomically claim the in-flight slot.

        Returns the locked report when this caller won the claim (status was
        idle or failed -> now running), or None when another generation is
        already running. Must be called inside a transaction.
        """
        locked = Report.objects.select_for_update().get(pk=report.pk)
        if locked.generation_status == Report.GenerationStatus.RUNNING:
            return None
        locked.generation_status = Report.GenerationStatus.RUNNING
        locked.generation_error = None
        locked.save(
            update_fields=["generation_status", "generation_error", "updated_at"]
        )
        return locked

    @staticmethod
    def ensure_report_for_sample(*, sample_id: uuid.UUID) -> Report:
        """RP-1: get-or-create the draft report row for a ready sample."""
        report, _ = Report.objects.get_or_create(
            sample_id=sample_id,
            defaults={
                "status": Report.Status.DRAFT,
                "current_version": 0,
            },
        )
        return report

    @staticmethod
    def enqueue_generation_for_sample(
        *, sample_id: uuid.UUID, actor: StaffUser
    ) -> bool:
        """RP-1 hook: sample just became ready -> ensure the draft report row
        and enqueue reports.generate_pdf (exactly-once per ready transition).

        Returns True when a generation was enqueued.
        """
        with transaction.atomic():
            report = ReportService.ensure_report_for_sample(sample_id=sample_id)
            if report.status == Report.Status.VOID:
                return False
            locked = ReportService._claim_generation(report)
            if locked is None:
                return False
            _enqueue_generate_pdf(locked.id, actor.id, locked.current_version + 1)
            return True

    @staticmethod
    def regenerate_report(
        *,
        report_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/reports/{id}/regenerate (§6.7).

        Enqueues reports.generate_pdf for a new version from the current
        approved results. -> 202 with the report state. 409 report_void;
        409 generation_already_running. The named user is recorded as the
        generated_by trigger in audit.
        """
        with transaction.atomic():
            report = ReportService._get_report(report_id)
            if report.status == Report.Status.VOID:
                raise ReportVoidError("Report is void and cannot be regenerated.")
            locked = ReportService._claim_generation(report)
            if locked is None:
                raise GenerationAlreadyRunningError(
                    "A PDF generation is already in flight for this report."
                )
            AuditLog.objects.create(
                actor_id=actor.id,
                action="report.regenerate_requested",
                entity_type="report",
                entity_id=locked.id,
                before_jsonb={
                    "status": locked.status,
                    "current_version": locked.current_version,
                },
                after_jsonb={
                    "generated_by": str(actor.id),
                    "generated_by_email": actor.email,
                    "generation_status": Report.GenerationStatus.RUNNING,
                },
                ip=ip,
                user_agent=user_agent,
            )
            _enqueue_generate_pdf(locked.id, actor.id, locked.current_version + 1)
            return {
                "id": str(locked.id),
                "sample_id": str(locked.sample_id),
                "status": locked.status,
                "current_version": locked.current_version,
                "generation_status": Report.GenerationStatus.RUNNING,
            }
