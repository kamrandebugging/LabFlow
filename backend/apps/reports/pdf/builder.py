"""
LAB-29 (KAN-154): assemble a ReportContext from Django models.

The builder is the only place that touches the ORM. Everything downstream
(rendering, QR, template) works on plain dataclasses, which keeps the
golden-file test deterministic and DB-free.

Reference intervals (§9.1: "the reference interval actually used") are
recomputed at build time with the LAB-24 pure engine (select_range) using
the sample's collection date — the same rule the entry path used. Ranges
are effective-dated, so a range edited after entry resolves identically
for the collection date.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

from .context import (
    AmendedTestLine,
    LabInfo,
    OrderInfo,
    PatientInfo,
    ReportContext,
    ResultGroup,
    ResultRow,
    SampleInfo,
    Signatory,
    UrduBlock,
    VersionHistoryEntry,
)
from .qr import make_qr_data_uri, qr_payload_for_report
from .ur import REPORT_READY_UR

if TYPE_CHECKING:
    from apps.billing.models import Invoice
    from apps.reports.models import Report

KARACHI = ZoneInfo("Asia/Karachi")

FLAG_DISPLAY = {"low": "L", "high": "H", "critical": "CRITICAL"}


def _fmt_dt(dt: datetime | None) -> str:
    """Format an aware datetime in Asia/Karachi for the report."""
    if dt is None:
        return ""
    local = dt.astimezone(KARACHI)
    return local.strftime("%d %b %Y, %H:%M PKT")


def format_age(dob: date | None, on: date) -> str:
    """PT-6: age in years, months or days as fits, else 'Age: not recorded'."""
    if dob is None:
        return "Age: not recorded"
    days = (on - dob).days
    if days < 0:
        return "Age: not recorded"
    if days < 60:
        return f"{days} days"
    months = days // 30
    if months < 24:
        return f"{months} months"
    return f"{months // 12} years"


def _build_interval_lookup(
    test_ids: list[UUID],
    collected_on: date,
    patient_sex: str,
    age_days: int | None,
) -> dict[UUID, str]:
    """
    Batch the reference-interval lookup for all tests (avoids N+1).

    Returns {test_id: "low – high unit"} via the LAB-24 engine; ""
    when no range applies (qualitative / no match — flag None by design).
    """
    from apps.catalog.models import ReferenceRange
    from apps.results.engine import RangeRow, select_range

    ranges_by_test: dict[UUID, list[ReferenceRange]] = {}
    for r in ReferenceRange.objects.filter(test_id__in=test_ids):
        ranges_by_test.setdefault(r.test_id, []).append(r)

    out: dict[UUID, str] = {}
    for tid in test_ids:
        models = ranges_by_test.get(tid, [])
        if not models:
            out[tid] = ""
            continue
        row_by_id: dict[int, ReferenceRange] = {}
        rows: list[RangeRow] = []
        for r in models:
            rr = RangeRow(
                sex=r.sex,
                age_min_days=r.age_min_days,
                age_max_days=r.age_max_days,
                effective_from=r.effective_from,
                effective_to=r.effective_to,
                low=r.low,
                high=r.high,
                critical_low=r.critical_low,
                critical_high=r.critical_high,
                test_id=r.test_id,
                created_at=r.created_at,
            )
            row_by_id[id(rr)] = r
            rows.append(rr)
        picked = select_range(
            rows,
            patient_sex=patient_sex,
            age_in_days=age_days,
            collection_date=collected_on,
        )
        if picked is None or (picked.low is None and picked.high is None):
            out[tid] = ""
            continue
        model = row_by_id[id(picked)]
        low = f"{picked.low}" if picked.low is not None else "…"
        high = f"{picked.high}" if picked.high is not None else "…"
        unit = f" {model.unit}" if model.unit else ""
        out[tid] = f"{low} – {high}{unit}"
    return out


def _build_panel_lookup(test_ids: list[UUID], invoice: Invoice) -> dict[UUID, str]:
    """
    Batch the panel-name lookup for all tests (avoids N+1).

    Returns {test_id: panel_name} for tests in a panel on the invoice.
    """
    from apps.billing.models import InvoiceItem
    from apps.catalog.models import PanelTest

    panel_ids = set(
        InvoiceItem.objects.filter(invoice=invoice)
        .exclude(panel_id__isnull=True)
        .values_list("panel_id", flat=True)
    )
    if not panel_ids:
        return {}
    out: dict[UUID, str] = {}
    for link in PanelTest.objects.filter(
        test_id__in=test_ids, panel_id__in=panel_ids
    ).select_related("panel"):
        out.setdefault(link.test_id, link.panel.name)
    return out


def build_report_context(report: Report, version: int) -> ReportContext:
    """
    Assemble the render context for one report version.

    Raises ValueError if the report is not finalised (T-34: a failed
    generation leaves no report_version row and the report stays draft —
    the future Celery task must call this before rendering).
    """
    from django.core.exceptions import ObjectDoesNotExist

    from apps.results.models import Result, ResultApproval
    from apps.samples.models import SampleEvent

    if report.status not in ("final", "amended") or report.finalised_at is None:
        raise ValueError(
            f"Report {report.id} is not finalised (status={report.status}); "
            "refusing to render."
        )
    try:
        report.versions.get(version=version)
    except ObjectDoesNotExist as exc:
        raise ValueError(f"Report {report.id} has no version {version}") from exc

    sample = report.sample
    invoice = sample.invoice
    patient = invoice.patient
    branch = sample.branch

    # Tenant (lab) name — resolved from the current schema's tenant.
    from django.db import connection

    tenant = connection.tenant  # type: ignore[attr-defined]
    lab_name = getattr(tenant, "name", "Diagnostic Lab")

    received_event = (
        SampleEvent.objects.filter(sample=sample, event="RECEIVED")
        .order_by("created_at")
        .first()
    )

    # Approved results for this sample (amended rows are superseded history;
    # the live set is status=approved).
    results = (
        Result.objects.filter(sample=sample, status="approved")
        .select_related("test", "entered_by")
        .order_by("created_at")
    )

    # Signatories: each approving pathologist once (R-13).
    approvals = (
        ResultApproval.objects.filter(result__sample=sample, decision="approved")
        .select_related("pathologist")
        .order_by("created_at")
    )
    seen: set[str] = set()
    signatories: list[Signatory] = []
    for ap in approvals:
        key = str(ap.pathologist_id)
        if key in seen:
            continue
        seen.add(key)
        signatories.append(
            Signatory(
                name=ap.pathologist.email,
                role="Pathologist",
                approved_at=_fmt_dt(ap.created_at),
            )
        )

    # Result rows with panel grouping (batched lookups — no N+1).
    results_list = list(results)
    test_ids = [r.test_id for r in results_list]
    dob = patient.date_of_birth
    age_days = (sample.collected_at.date() - dob).days if dob else None
    intervals = _build_interval_lookup(
        test_ids, sample.collected_at.date(), patient.sex, age_days
    )
    panels = _build_panel_lookup(test_ids, invoice)
    groups: dict[str | None, list[ResultRow]] = {}
    for r in results_list:
        panel_name = panels.get(r.test_id)
        comments_parts: list[str] = []
        for ap in approvals:
            if ap.result_id == r.id and ap.note:
                comments_parts.append(ap.note)
                if ap.range_override:
                    comments_parts.append("(range override)")
        groups.setdefault(panel_name, []).append(
            ResultRow(
                test_name=r.test.name,
                panel_name=panel_name,
                value=r.value,
                unit=r.unit or "",
                flag_display=FLAG_DISPLAY.get(r.flag or "", ""),
                reference_interval=intervals[r.test_id],
                comments="; ".join(comments_parts),
                is_changed=False,
            )
        )
    # Panel groups first (in first-seen order), then standalone tests.
    result_groups = [
        ResultGroup(panel_name=name, rows=rows)
        for name, rows in groups.items()
        if name is not None
    ] + [
        ResultGroup(panel_name=None, rows=rows)
        for name, rows in groups.items()
        if name is None
    ]

    # Amendment data (§9.4).
    is_amended = version > 1
    amended_lines: list[AmendedTestLine] = []
    if is_amended:
        # Changed tests: results whose supersedes chain was approved in
        # this version. We list amendments approved for this version.
        amended_results = Result.objects.filter(
            sample=sample, status="approved"
        ).exclude(supersedes__isnull=True)
        for r in amended_results.select_related("test"):
            old = r.supersedes
            latest_ap = (
                ResultApproval.objects.filter(result=r, decision="approved")
                .order_by("-created_at")
                .first()
            )
            approver = latest_ap.pathologist.email if latest_ap is not None else ""
            amended_lines.append(
                AmendedTestLine(
                    test_name=r.test.name,
                    previous_value=old.value if old else "",
                    previous_unit=old.unit if old and old.unit else "",
                    corrected_value=r.value,
                    corrected_unit=r.unit or "",
                    amendment_date=_fmt_dt(r.created_at),
                    approving_pathologist=approver,
                )
            )
        # Mark changed rows with daggers.
        changed_names = {r.test.name for r in amended_results}
        rebuilt: list[ResultGroup] = []
        for g in result_groups:
            new_rows = [
                ResultRow(
                    test_name=row.test_name,
                    panel_name=row.panel_name,
                    value=row.value,
                    unit=row.unit,
                    flag_display=row.flag_display,
                    reference_interval=row.reference_interval,
                    comments=row.comments,
                    is_changed=row.test_name in changed_names,
                )
                for row in g.rows
            ]
            rebuilt.append(ResultGroup(panel_name=g.panel_name, rows=new_rows))
        result_groups = rebuilt

    version_history = [
        VersionHistoryEntry(
            version=v.version,
            status="Amended" if v.version > 1 else "Final",
            finalised_at=_fmt_dt(report.finalised_at),
        )
        for v in report.versions.order_by("version")
    ]

    # QR (§9.3): placeholder token until the delivery LAB issues real ones.
    # The token printed is the token current at generation time.
    token = f"placeholder-{report.id}-v{version}"
    access_url = qr_payload_for_report(token)

    ctx = ReportContext(
        lab=LabInfo(
            name=lab_name,
            branch_name=branch.name,
            branch_address=branch.address or "",
            phone=branch.phone or "",
        ),
        report_id=str(report.id),
        version=version,
        version_label=f"Version {version}"
        + (" — Amended report" if is_amended else ""),
        status="Amended" if is_amended else "Final",
        finalised_at=_fmt_dt(report.finalised_at),
        patient=PatientInfo(
            name=patient.name,
            mrn=patient.mrn,
            age_display=format_age(patient.date_of_birth, sample.collected_at.date()),
            sex=patient.get_sex_display(),
            dob=patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            phone=patient.phone,
        ),
        order=OrderInfo(
            clinician=invoice.referral_partner.name
            if invoice.referral_partner is not None
            else "Walk-in",
            invoice_number=str(invoice.id),
        ),
        sample=SampleInfo(
            accession_id=sample.accession_id,
            collected_at=_fmt_dt(sample.collected_at),
            received_at=_fmt_dt(received_event.created_at) if received_event else None,
            status_notes="",
        ),
        is_amended=is_amended,
        corrects_version=version - 1 if is_amended else None,
        amended_lines=amended_lines,
        version_history=version_history,
        result_groups=result_groups,
        signatories=signatories,
        urdu=UrduBlock(
            lab_name=lab_name,
            patient_name=patient.name,
            accession_id=sample.accession_id,
            ready_sentence=REPORT_READY_UR,
            phone=branch.phone or "",
        ),
        qr_data_uri=make_qr_data_uri(access_url),
        access_url=access_url,
    )
    return ctx
