"""
LAB-29 (KAN-154): plain-data report context.

The render boundary is pure: render_report_pdf() takes a ReportContext,
never Django models. This keeps the WeasyPrint template testable without
a database and makes the golden-file test deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LabInfo:
    name: str
    branch_name: str
    branch_address: str
    phone: str


@dataclass(frozen=True)
class PatientInfo:
    name: str
    mrn: str
    age_display: str  # "34 years" | "8 months" | "12 days" | "Age: not recorded"
    sex: str
    dob: str | None
    phone: str


@dataclass(frozen=True)
class OrderInfo:
    clinician: str  # referring partner/clinician name, or "Walk-in"
    invoice_number: str


@dataclass(frozen=True)
class SampleInfo:
    accession_id: str
    collected_at: str
    received_at: str | None
    status_notes: str


@dataclass(frozen=True)
class ResultRow:
    test_name: str
    panel_name: str | None
    value: str  # exactly as entered — the template must never reformat
    unit: str
    flag_display: str  # "L" | "H" | "CRITICAL" | "" (blank for normal)
    reference_interval: str  # the interval actually used, with its unit
    comments: str  # pathologist notes / override comments
    is_changed: bool  # dagger mark on amended versions


@dataclass(frozen=True)
class ResultGroup:
    panel_name: str | None  # None = standalone (non-panel) tests
    rows: list[ResultRow] = field(default_factory=list)


@dataclass(frozen=True)
class Signatory:
    name: str
    role: str
    approved_at: str


@dataclass(frozen=True)
class AmendedTestLine:
    test_name: str
    previous_value: str
    previous_unit: str
    corrected_value: str
    corrected_unit: str
    amendment_date: str
    approving_pathologist: str


@dataclass(frozen=True)
class VersionHistoryEntry:
    version: int
    status: str
    finalised_at: str


@dataclass(frozen=True)
class UrduBlock:
    """Patient-usability summary only — never clinical content (§9.2)."""

    lab_name: str
    patient_name: str
    accession_id: str
    ready_sentence: str  # fixed ur string, never free-typed
    phone: str


@dataclass(frozen=True)
class ReportContext:
    lab: LabInfo
    report_id: str
    version: int
    version_label: str  # "Version 1" | "Version 2 — Amended report"
    status: str  # "Final" | "Amended"
    finalised_at: str  # Asia/Karachi, pre-formatted
    patient: PatientInfo
    order: OrderInfo
    sample: SampleInfo
    is_amended: bool
    corrects_version: int | None
    amended_lines: list[AmendedTestLine] = field(default_factory=list)
    version_history: list[VersionHistoryEntry] = field(default_factory=list)
    result_groups: list[ResultGroup] = field(default_factory=list)
    signatories: list[Signatory] = field(default_factory=list)
    urdu: UrduBlock | None = None
    qr_data_uri: str = ""
    access_url: str = ""
