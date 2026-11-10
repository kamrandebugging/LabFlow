"""Query and exception aggregation services for Reports (Doc 03 §5.6, §6.1, §6.7).

Provides:
- ReportQueryService: list_reports (cursor pagination, branch scoping, filtering)
  and get_report_detail.
- ReportExceptionsService: get_exceptions (aggregating actionable exceptions
  from real model fields).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db.models import Prefetch, Q
from django.utils import timezone as dj_timezone

from apps.accounts.models import Role, StaffUser
from apps.platform.settings_accessor import get_setting
from apps.reports.models import (
    Report,
    ReportAccessToken,
    ReportDelivery,
    ReportVersion,
)
from apps.results.models import Result
from apps.samples.models import Sample, SampleTransfer

REPORT_READ_ROLES = {
    Role.OWNER,
    Role.MANAGER,
    Role.RECEPTION,
    Role.TECHNICIAN,
    Role.PATHOLOGIST,
    "owner",
    "manager",
    "reception",
    "receptionist",
    "technician",
    "pathologist",
}

LIST_DEFAULT_LIMIT = 50
LIST_MAX_LIMIT = 200


def _age_years(dob: Any, collected_at: Any) -> int | None:
    """Whole years between date of birth and specimen collection."""
    if not dob:
        return None
    reference = collected_at.date() if collected_at else dj_timezone.now().date()
    years = (reference - dob).days // 365
    return years if years >= 0 else None


class ReportQueryError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "report_error",
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


def _encode_cursor(created_at: datetime, report_id: uuid.UUID) -> str:
    payload = {"created_at": created_at.isoformat(), "id": str(report_id)}
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        payload = json.loads(raw)
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        report_id = uuid.UUID(str(payload["id"]))
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise ReportQueryError(
            "Invalid cursor.", code="validation_error", status_code=422
        ) from exc
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at, report_id


def _parse_datetime(value: Any, name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        raise ReportQueryError(
            f"Invalid {name}: expected ISO 8601 datetime.",
            code="validation_error",
            status_code=422,
        ) from None


class ReportQueryService:
    @staticmethod
    def list_reports(
        *,
        actor: StaffUser,
        status: str | None = None,
        branch_id: str | None = None,
        patient: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        cursor: str | None = None,
        limit: int = LIST_DEFAULT_LIMIT,
    ) -> tuple[list[dict[str, Any]], str | None]:
        qs = (
            Report.objects.scoped_to(actor)
            .select_related("sample", "sample__branch", "sample__invoice__patient")
            .prefetch_related(
                "sample__sample_tests__test",
                Prefetch(
                    "deliveries",
                    queryset=ReportDelivery.objects.order_by("-created_at"),
                ),
            )
            .order_by("-created_at", "-id")
        )

        if status is not None:
            if status not in Report.Status.values:
                clean_status = str(status)[:30]
                raise ReportQueryError(
                    f"Unknown status filter: '{clean_status}'.",
                    code="validation_error",
                    status_code=422,
                )
            qs = qs.filter(status=status)

        if branch_id is not None:
            try:
                b_uuid = uuid.UUID(str(branch_id))
            except (ValueError, TypeError, AttributeError):
                raise ReportQueryError(
                    "Invalid branch identifier.",
                    code="validation_error",
                    status_code=422,
                ) from None
            qs = qs.filter(sample__branch_id=b_uuid)

        if patient is not None and str(patient).strip():
            query = str(patient).strip()[:100]
            try:
                p_uuid = uuid.UUID(query)
                qs = qs.filter(sample__invoice__patient_id=p_uuid)
            except (ValueError, TypeError):
                qs = qs.filter(
                    Q(sample__invoice__patient__name__icontains=query)
                    | Q(sample__invoice__patient__mrn__icontains=query)
                    | Q(sample__accession_id__icontains=query)
                )

        if created_after is not None:
            dt_after = _parse_datetime(created_after, "created_after")
            qs = qs.filter(created_at__gte=dt_after)

        if created_before is not None:
            dt_before = _parse_datetime(created_before, "created_before")
            qs = qs.filter(created_at__lte=dt_before)

        if cursor is not None:
            c_created, c_id = _decode_cursor(cursor)
            qs = qs.filter(
                Q(created_at__lt=c_created) | Q(created_at=c_created, id__lt=c_id)
            )

        limit_val = max(1, min(limit, LIST_MAX_LIMIT))
        rows = list(qs[: limit_val + 1])
        next_cursor = None
        if len(rows) > limit_val:
            last = rows[limit_val - 1]
            next_cursor = _encode_cursor(last.created_at, last.id)
            rows = rows[:limit_val]

        results = []
        for r in rows:
            sample = r.sample
            patient_obj = sample.invoice.patient
            tests = [st.test.name for st in sample.sample_tests.all()]
            latest_del = r.deliveries.all()
            del_status = latest_del[0].status if latest_del else None
            results.append(
                {
                    "id": str(r.id),
                    "sample_id": str(sample.id),
                    "accession_id": sample.accession_id,
                    "status": r.status,
                    "current_version": r.current_version,
                    "generation_status": r.generation_status,
                    "generation_error": r.generation_error,
                    "finalised_at": r.finalised_at.isoformat()
                    if r.finalised_at
                    else None,
                    "created_at": r.created_at.isoformat(),
                    "updated_at": r.updated_at.isoformat(),
                    "branch_id": str(sample.branch_id),
                    "branch_name": sample.branch.name if sample.branch else "",
                    "patient_id": str(patient_obj.id),
                    "patient_mrn": patient_obj.mrn,
                    "patient_name": patient_obj.name,
                    "tests": tests,
                    "delivery_status": del_status,
                }
            )

        return results, next_cursor

    @staticmethod
    def get_report_detail(*, report_id: uuid.UUID, actor: StaffUser) -> dict[str, Any]:
        try:
            report = (
                Report.objects.scoped_to(actor)
                .select_related(
                    "sample",
                    "sample__branch",
                    "sample__invoice__patient",
                    "sample__collected_by",
                )
                .prefetch_related(
                    "sample__sample_tests__test",
                    "sample__results__test",
                    "sample__invoice__patient__contacts",
                    Prefetch(
                        "versions",
                        queryset=ReportVersion.objects.select_related(
                            "generated_by"
                        ).order_by("-version"),
                    ),
                    Prefetch(
                        "deliveries",
                        queryset=ReportDelivery.objects.select_related(
                            "contact"
                        ).order_by("-created_at"),
                    ),
                    Prefetch(
                        "access_tokens",
                        queryset=ReportAccessToken.objects.order_by("-created_at"),
                    ),
                )
                .get(id=report_id)
            )
        except Report.DoesNotExist:
            raise ReportQueryError(
                "Report not found.", code="report_not_found", status_code=404
            ) from None

        sample = report.sample
        patient = sample.invoice.patient
        now = dj_timezone.now()

        results_list = [
            {
                "id": str(res.id),
                "test_name": res.test.name,
                "test_code": res.test.code,
                "value": res.value,
                "unit": res.unit,
                "flag": res.flag,
                "status": res.status,
                "amend_reason": res.amend_reason,
            }
            for res in sample.results.all()
        ]

        versions_list = [
            {
                "id": str(v.id),
                "version": v.version,
                "pdf_key": v.pdf_key,
                "generated_by_id": str(v.generated_by_id)
                if v.generated_by_id
                else None,
                "generated_by_email": v.generated_by.email if v.generated_by else None,
                "created_at": v.created_at.isoformat(),
            }
            for v in report.versions.all()
        ]

        deliveries_list = [
            {
                "id": str(d.id),
                "channel": d.channel,
                "status": d.status,
                "contact_id": str(d.contact_id),
                "contact_value": d.contact.value if d.contact else None,
                "contact_type": d.contact.kind if d.contact else None,
                "contact_kind": d.contact.kind if d.contact else None,
                "attempts": d.attempts,
                "next_attempt_at": d.next_attempt_at.isoformat()
                if d.next_attempt_at
                else None,
                "last_error": d.last_error,
                "sent_at": d.sent_at.isoformat() if d.sent_at else None,
                "created_at": d.created_at.isoformat(),
            }
            for d in report.deliveries.all()
        ]

        tokens_list = [
            {
                "id": str(t.id),
                "expires_at": t.expires_at.isoformat(),
                "revoked_at": t.revoked_at.isoformat() if t.revoked_at else None,
                "last_accessed_at": t.last_accessed_at.isoformat()
                if t.last_accessed_at
                else None,
                "is_active": t.revoked_at is None and t.expires_at > now,
                "created_at": t.created_at.isoformat(),
            }
            for t in report.access_tokens.all()
        ]

        return {
            "id": str(report.id),
            "status": report.status,
            "current_version": report.current_version,
            "finalised_at": report.finalised_at.isoformat()
            if report.finalised_at
            else None,
            "generation_status": report.generation_status,
            "generation_error": report.generation_error,
            "branding": {
                "display_name": get_setting("brand_display_name"),
                "accent_colour": get_setting("brand_accent_colour"),
            },
            "created_at": report.created_at.isoformat(),
            "updated_at": report.updated_at.isoformat(),
            "sample": {
                "id": str(sample.id),
                "accession_id": sample.accession_id,
                "status": sample.status,
                "collected_at": sample.collected_at.isoformat()
                if sample.collected_at
                else None,
                "branch": {
                    "id": str(sample.branch.id),
                    "name": sample.branch.name,
                    "code": getattr(sample.branch, "code", ""),
                },
            },
            "patient": {
                "id": str(patient.id),
                "mrn": patient.mrn,
                "name": patient.name,
                "full_name": patient.name,
                "dob": patient.date_of_birth.isoformat()
                if patient.date_of_birth
                else None,
                "date_of_birth": patient.date_of_birth.isoformat()
                if patient.date_of_birth
                else None,
                "age_years": _age_years(patient.date_of_birth, sample.collected_at),
                "sex": patient.sex,
                "gender": patient.sex,
                "phone": patient.phone,
                "email": next(
                    (c.value for c in patient.contacts.all() if c.kind == "email"),
                    None,
                ),
                "contacts": [
                    {
                        "id": str(c.id),
                        "kind": c.kind,
                        "value": c.value,
                        "is_primary": c.is_primary,
                    }
                    for c in patient.contacts.all()
                ],
            },
            "results": results_list,
            "versions": versions_list,
            "deliveries": deliveries_list,
            "access_tokens": tokens_list,
        }


class ReportExceptionsService:
    @staticmethod
    def get_exceptions(*, actor: StaffUser) -> dict[str, Any]:
        now = dj_timezone.now()
        results: list[dict[str, Any]] = []

        # 1. Failed generation
        failed_reports = (
            Report.objects.scoped_to(actor)
            .filter(
                Q(generation_status=Report.GenerationStatus.FAILED)
                | (Q(generation_error__isnull=False) & ~Q(generation_error=""))
            )
            .select_related("sample", "sample__branch", "sample__invoice__patient")
            .order_by("-updated_at")[:100]
        )
        for r in failed_reports:
            sample = getattr(r, "sample", None)
            accession_id = sample.accession_id if sample else ""
            invoice = getattr(sample, "invoice", None) if sample else None
            patient = getattr(invoice, "patient", None) if invoice else None
            branch = getattr(sample, "branch", None) if sample else None
            results.append(
                {
                    "id": f"gen-{r.id}",
                    "kind": "failed_generation",
                    "title": f"Report generation failed ({accession_id})",
                    "severity": "error",
                    "reference_id": str(r.id),
                    "reference_code": accession_id,
                    "patient_name": patient.name if patient else None,
                    "branch_name": branch.name if branch else None,
                    "created_at": r.updated_at.isoformat(),
                    "details": {
                        "report_id": str(r.id),
                        "status": r.status,
                        "generation_status": r.generation_status,
                        "generation_error": r.generation_error,
                        "current_version": r.current_version,
                    },
                }
            )

        # 2. Failed deliveries
        if actor.is_tenant_wide:
            failed_deliveries_qs = ReportDelivery.objects.filter(
                status__in=[
                    ReportDelivery.Status.FAILED,
                    ReportDelivery.Status.BOUNCED,
                ],
            )
        else:
            branch_ids = actor.assigned_branch_ids()
            if not branch_ids:
                failed_deliveries_qs = ReportDelivery.objects.none()
            else:
                failed_deliveries_qs = ReportDelivery.objects.filter(
                    report__sample__branch_id__in=branch_ids,
                    status__in=[
                        ReportDelivery.Status.FAILED,
                        ReportDelivery.Status.BOUNCED,
                    ],
                )

        failed_deliveries = failed_deliveries_qs.select_related(
            "report__sample__branch",
            "report__sample__invoice__patient",
            "contact",
        ).order_by("-updated_at")[:100]
        for d in failed_deliveries:
            report = getattr(d, "report", None)
            sample = getattr(report, "sample", None) if report else None
            accession_id = sample.accession_id if sample else ""
            invoice = getattr(sample, "invoice", None) if sample else None
            patient = getattr(invoice, "patient", None) if invoice else None
            branch = getattr(sample, "branch", None) if sample else None
            ch = getattr(d, "channel", None)
            channel_title = ch.capitalize() if ch else "Channel"
            results.append(
                {
                    "id": f"del-{d.id}",
                    "kind": "failed_delivery",
                    "title": f"Failed delivery via {channel_title}",
                    "severity": "error",
                    "reference_id": str(d.report_id),
                    "reference_code": accession_id,
                    "patient_name": patient.name if patient else None,
                    "branch_name": branch.name if branch else None,
                    "created_at": d.updated_at.isoformat(),
                    "details": {
                        "delivery_id": str(d.id),
                        "report_id": str(d.report_id),
                        "channel": d.channel,
                        "delivery_status": d.status,
                        "contact": d.contact.value if d.contact else None,
                        "attempts": d.attempts,
                        "next_attempt_at": d.next_attempt_at.isoformat()
                        if d.next_attempt_at
                        else None,
                        "last_error": d.last_error,
                    },
                }
            )

        # 3. Late transfers (open transfers dispatched > 2 hours ago)
        late_threshold = now - timedelta(hours=2)
        transfer_qs = SampleTransfer.objects.filter(
            status=SampleTransfer.Status.OPEN,
            dispatched_at__lt=late_threshold,
        )
        if not actor.is_tenant_wide:
            branch_ids = actor.assigned_branch_ids()
            if not branch_ids:
                transfer_qs = transfer_qs.none()
            else:
                transfer_qs = transfer_qs.filter(
                    Q(from_branch_id__in=branch_ids) | Q(to_branch_id__in=branch_ids)
                )
        transfer_qs = transfer_qs.select_related(
            "sample", "from_branch", "to_branch", "sample__invoice__patient"
        ).order_by("dispatched_at")[:100]
        for t in transfer_qs:
            hours_late = (
                round((now - t.dispatched_at).total_seconds() / 3600.0, 1)
                if t.dispatched_at
                else 0
            )
            invoice = getattr(t.sample, "invoice", None)
            patient = getattr(invoice, "patient", None) if invoice else None
            patient_name = patient.name if patient else None
            xfer_title = f"Late transfer: {t.from_branch.name} -> {t.to_branch.name}"
            results.append(
                {
                    "id": f"xfer-{t.id}",
                    "kind": "late_transfer",
                    "title": xfer_title,
                    "severity": "warning",
                    "reference_id": str(t.sample_id),
                    "reference_code": t.sample.accession_id,
                    "patient_name": patient_name,
                    "branch_name": t.from_branch.name,
                    "created_at": t.dispatched_at.isoformat()
                    if t.dispatched_at
                    else t.created_at.isoformat(),
                    "details": {
                        "transfer_id": str(t.id),
                        "from_branch": t.from_branch.name,
                        "to_branch": t.to_branch.name,
                        "dispatched_at": t.dispatched_at.isoformat()
                        if t.dispatched_at
                        else None,
                        "hours_late": hours_late,
                        "status": t.status,
                    },
                }
            )

        # 4. Critical results unacknowledged
        critical_results = (
            Result.objects.scoped_to(actor)
            .filter(
                flag=Result.Flag.CRITICAL,
                status=Result.Status.APPROVED,
                critical_notifications__isnull=True,
            )
            .select_related(
                "sample", "sample__branch", "sample__invoice__patient", "test"
            )
            .order_by("created_at")[:100]
        )
        for cr in critical_results:
            crit_title = (
                f"Unacknowledged critical: {cr.test.name} ({cr.value} {cr.unit or ''})"
            )
            sample = cr.sample
            patient_name = None
            patient_mrn = None
            accession_id = ""
            branch_name = None
            if sample:
                accession_id = sample.accession_id
                if sample.branch:
                    branch_name = sample.branch.name
                invoice = getattr(sample, "invoice", None)
                if invoice and getattr(invoice, "patient", None):
                    patient_name = invoice.patient.name
                    patient_mrn = invoice.patient.mrn

            results.append(
                {
                    "id": f"crit-{cr.id}",
                    "kind": "critical_unacknowledged",
                    "title": crit_title,
                    "severity": "critical",
                    "reference_id": str(cr.sample_id),
                    "reference_code": accession_id,
                    "patient_name": patient_name,
                    "branch_name": branch_name,
                    "created_at": cr.created_at.isoformat(),
                    "details": {
                        "result_id": str(cr.id),
                        "sample_id": str(cr.sample_id),
                        "test_name": cr.test.name,
                        "test_code": cr.test.code,
                        "value": cr.value,
                        "unit": cr.unit,
                        "flag": cr.flag,
                        "patient_mrn": patient_mrn,
                    },
                }
            )

        # 5. Stuck samples
        stuck_threshold = now - timedelta(hours=4)
        stuck_samples = (
            Sample.objects.scoped_to(actor)
            .filter(
                status__in=[
                    Sample.Status.COLLECTED,
                    Sample.Status.RECEIVED,
                    Sample.Status.IN_PROCESS,
                ],
                collected_at__lt=stuck_threshold,
            )
            .select_related("branch", "invoice__patient")
            .order_by("collected_at")[:100]
        )
        for s in stuck_samples:
            patient_name = None
            if getattr(s, "invoice", None) and getattr(s.invoice, "patient", None):
                patient_name = s.invoice.patient.name
            collected_str = (
                s.collected_at.isoformat()
                if s.collected_at
                else s.created_at.isoformat()
            )
            results.append(
                {
                    "id": f"stuck-{s.id}",
                    "kind": "stuck_sample",
                    "title": f"Stuck sample: {s.accession_id} ({s.status})",
                    "severity": "warning",
                    "reference_id": str(s.id),
                    "reference_code": s.accession_id,
                    "patient_name": patient_name,
                    "branch_name": s.branch.name if s.branch else None,
                    "created_at": collected_str,
                    "details": {
                        "sample_id": str(s.id),
                        "accession_id": s.accession_id,
                        "sample_status": s.status,
                        "collected_at": collected_str,
                    },
                }
            )

        counts = {
            "total": len(results),
            "failed_generation": sum(
                1 for r in results if r["kind"] == "failed_generation"
            ),
            "failed_delivery": sum(
                1 for r in results if r["kind"] == "failed_delivery"
            ),
            "late_transfer": sum(1 for r in results if r["kind"] == "late_transfer"),
            "critical_unacknowledged": sum(
                1 for r in results if r["kind"] == "critical_unacknowledged"
            ),
            "stuck_sample": sum(1 for r in results if r["kind"] == "stuck_sample"),
        }

        return {"results": results, "counts": counts}
