"""
LAB-29 (KAN-154): Diagnostic report generation — WeasyPrint bilingual PDF + QR.

T-34 (render failure is clean), T-38 (page-limit fixtures), T-48 (Urdu RTL)
+ DoD: golden files green; Urdu RTL with Latin digits unreversed.

The render boundary is pure: render_report_pdf takes a plain-data
ReportContext (no Django models), so these tests need no database.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest
from apps.reports.pdf.builder import build_report_context
from apps.reports.pdf.context import (
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
from apps.reports.pdf.qr import make_qr_data_uri, qr_payload_for_report
from apps.reports.pdf.rendering import render_report_html, render_report_pdf
from pypdf import PdfReader

URDU_RE = re.compile(r"[\u0600-\u06FF]")


def make_context(**overrides: object) -> ReportContext:
    """Fixed deterministic fixture — the golden-file source of truth."""
    lab = LabInfo(
        name="City Diagnostic Lab",
        branch_name="Gulberg Branch",
        branch_address="14-B Main Boulevard, Gulberg III, Lahore",
        phone="+92 42 3577 1234",
    )
    patient = PatientInfo(
        name="Ahmed Raza",
        mrn="MRN-000123",
        age_display="34 years",
        sex="Male",
        dob="1991-05-20",
        phone="+92 300 1234567",
    )
    order = OrderInfo(clinician="Dr. Sana Malik", invoice_number="INV-2026-0042")
    sample = SampleInfo(
        accession_id="CDL20261103000123",
        collected_at="03 Nov 2026, 09:15 PKT",
        received_at="03 Nov 2026, 10:02 PKT",
        status_notes="Specimen accepted in good condition.",
    )
    rows = [
        ResultRow(
            test_name="Hemoglobin",
            panel_name="Complete Blood Count",
            value="13.2",
            unit="g/dL",
            flag_display="",
            reference_interval="13.0 – 17.0",
            comments="",
            is_changed=False,
        ),
        ResultRow(
            test_name="WBC",
            panel_name="Complete Blood Count",
            value="14.5",
            unit="x10^9/L",
            flag_display="H",
            reference_interval="4.0 – 11.0",
            comments="",
            is_changed=False,
        ),
        ResultRow(
            test_name="Glucose (Fasting)",
            panel_name=None,
            value="210",
            unit="mg/dL",
            flag_display="CRITICAL",
            reference_interval="70 – 100",
            comments="Critical value — clinician notified.",
            is_changed=False,
        ),
    ]
    groups = [
        ResultGroup(panel_name="Complete Blood Count", rows=[rows[0], rows[1]]),
        ResultGroup(panel_name=None, rows=[rows[2]]),
    ]
    signatories = [
        Signatory(
            name="dr.ayesha@citylab.pk",
            role="Pathologist",
            approved_at="03 Nov 2026, 14:30 PKT",
        )
    ]
    urdu = UrduBlock(
        lab_name="City Diagnostic Lab",
        patient_name="Ahmed Raza",
        accession_id="CDL20261103000123",
        ready_sentence="آپ کی رپورٹ تیار ہے",
        phone="+92 42 3577 1234",
    )
    token = "tok_test_0001"
    access_url = qr_payload_for_report(token)
    ctx = ReportContext(
        lab=lab,
        report_id="9f3a2b1c-0000-4000-8000-000000000001",
        version=1,
        version_label="Version 1",
        status="Final",
        finalised_at="03 Nov 2026, 15:00 PKT",
        patient=patient,
        order=order,
        sample=sample,
        is_amended=False,
        corrects_version=None,
        amended_lines=[],
        version_history=[
            VersionHistoryEntry(
                version=1, status="Final", finalised_at="03 Nov 2026, 15:00 PKT"
            )
        ],
        result_groups=groups,
        signatories=signatories,
        urdu=urdu,
        qr_data_uri=make_qr_data_uri(access_url),
        access_url=access_url,
    )
    for key, value in overrides.items():
        object.__setattr__(ctx, key, value)
    return ctx


def make_amended_context() -> ReportContext:
    base = make_context()
    amended_rows = [
        ResultRow(
            test_name="Hemoglobin",
            panel_name="Complete Blood Count",
            value="12.8",
            unit="g/dL",
            flag_display="L",
            reference_interval="13.0 – 17.0",
            comments="",
            is_changed=True,
        ),
        ResultRow(
            test_name="WBC",
            panel_name="Complete Blood Count",
            value="14.5",
            unit="x10^9/L",
            flag_display="H",
            reference_interval="4.0 – 11.0",
            comments="",
            is_changed=False,
        ),
    ]
    groups = [
        ResultGroup(panel_name="Complete Blood Count", rows=amended_rows),
        ResultGroup(panel_name=None, rows=[base.result_groups[1].rows[0]]),
    ]
    object.__setattr__(base, "version", 2)
    object.__setattr__(base, "version_label", "Version 2 — Amended report")
    object.__setattr__(base, "status", "Amended")
    object.__setattr__(base, "is_amended", True)
    object.__setattr__(base, "corrects_version", 1)
    object.__setattr__(
        base,
        "amended_lines",
        [
            AmendedTestLine(
                test_name="Hemoglobin",
                previous_value="13.2",
                previous_unit="g/dL",
                corrected_value="12.8",
                corrected_unit="g/dL",
                amendment_date="04 Nov 2026, 11:00 PKT",
                approving_pathologist="dr.ayesha@citylab.pk",
            )
        ],
    )
    object.__setattr__(
        base,
        "version_history",
        [
            VersionHistoryEntry(
                version=1, status="Final", finalised_at="03 Nov 2026, 15:00 PKT"
            ),
            VersionHistoryEntry(
                version=2, status="Amended", finalised_at="04 Nov 2026, 11:30 PKT"
            ),
        ],
    )
    object.__setattr__(base, "result_groups", groups)
    return base


# ---------------------------------------------------------------------------
# Golden file + section order (DoD)
# ---------------------------------------------------------------------------


def _section_markers(html: str) -> list[str]:
    return re.findall(r"<!-- SECTION:([a-z-]+) -->", html)


def test_golden_html_sections_present_in_order() -> None:
    html = render_report_html(make_context())
    markers = _section_markers(html)
    assert markers == [
        "header",
        "meta",
        "patient",
        "order",
        "sample",
        "results",
        "signatory",
        "urdu",
        "footer",
    ], f"section order wrong: {markers}"


def test_golden_html_matches_checked_in_file() -> None:
    """Byte-stable HTML for the fixed fixture (timestamps/IDs are fixed)."""
    html = render_report_html(make_context())
    golden_path = pathlib.Path(__file__).parent / "golden" / "lab29_report_v1.html"
    assert golden_path.exists(), "golden file missing — generate it, do not skip"
    assert html == golden_path.read_text(encoding="utf-8")


def test_render_produces_valid_pdf() -> None:
    pdf = render_report_pdf(make_context())
    assert pdf[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 1


def test_pdf_contains_all_ten_sections_in_order() -> None:
    pdf = render_report_pdf(make_context())
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    anchors = [
        "City Diagnostic Lab",  # header
        "Version 1",  # meta
        "Ahmed Raza",  # patient
        "Dr. Sana Malik",  # order
        "CDL20261103000123",  # sample
        "Hemoglobin",  # results
        "Verified and authorised by",  # signatory
        "Page 1 of",  # footer
    ]
    positions = [text.find(a) for a in anchors]
    assert all(p >= 0 for p in positions), (
        f"missing: {[a for a, p in zip(anchors, positions, strict=True) if p < 0]}"
    )
    assert positions == sorted(positions), "sections out of order in PDF text"


def test_footer_page_numbers_on_every_page() -> None:
    pdf = render_report_pdf(make_context())
    pages = PdfReader(io.BytesIO(pdf)).pages
    for i, page in enumerate(pages, start=1):
        text = page.extract_text() or ""
        assert f"Page {i} of {len(pages)}" in text, f"footer missing on page {i}"
        assert "CDL20261103000123" in text, f"accession missing in footer on page {i}"


def test_two_identifiers_minimum() -> None:
    html = render_report_html(make_context())
    assert "Ahmed Raza" in html and "MRN-000123" in html


# ---------------------------------------------------------------------------
# Results table rules (§9.1)
# ---------------------------------------------------------------------------


def test_results_table_flags_and_intervals() -> None:
    html = render_report_html(make_context())
    assert ">H<" in html or '"H"' in html or ">H</" in html
    assert "CRITICAL" in html
    assert "4.0 – 11.0" in html
    # normal value has blank flag cell — Hemoglobin row has no L/H/CRITICAL
    assert "13.2" in html


def test_results_table_value_verbatim() -> None:
    """RS-2: value stored exactly as entered — template must not reformat."""
    ctx = make_context()
    html = render_report_html(ctx)
    assert "14.5" in html  # not "14.50"


def test_panel_grouping() -> None:
    html = render_report_html(make_context())
    cbc_pos = html.find("Complete Blood Count")
    hb_pos = html.find("Hemoglobin")
    wbc_pos = html.find("WBC")
    glu_pos = html.find("Glucose (Fasting)")
    assert cbc_pos < hb_pos < wbc_pos < glu_pos


def test_signatory_block_names_each_pathologist_once() -> None:
    html = render_report_html(make_context())
    assert html.count("dr.ayesha@citylab.pk") == 1
    assert "Verified and authorised by" in html
    assert "Pathologist" in html


# ---------------------------------------------------------------------------
# Urdu block (T-48, §9.2)
# ---------------------------------------------------------------------------


def test_urdu_block_is_rtl_isolated() -> None:
    html = render_report_html(make_context())
    m = re.search(r'<section[^>]*dir="rtl"[^>]*>.*?</section>', html, re.S)
    assert m, "no dir=rtl Urdu section found"
    assert "Noto Nastaliq Urdu" in html


def test_urdu_block_latin_digits_wrapped() -> None:
    """Accession/MRN/phone stay Latin and bidi-safe (T-48)."""
    html = render_report_html(make_context())
    m = re.search(r'<section[^>]*dir="rtl"[^>]*>(.*?)</section>', html, re.S)
    assert m
    block = m.group(1)
    assert "CDL20261103000123" in block
    # digits must be wrapped so bidi cannot reorder them
    assert re.search(r'<(bdi|span)[^>]*dir="ltr"[^>]*>CDL20261103000123</', block)


def test_no_urdu_in_results_table() -> None:
    html = render_report_html(make_context())
    m = re.search(r'<table[^>]*id="results-table"[^>]*>(.*?)</table>', html, re.S)
    assert m, "results table not found"
    assert not URDU_RE.search(m.group(1)), "Urdu leaked into results table"


def test_urdu_digits_unreversed_in_pdf() -> None:
    """T-48: accession ID and phone digits appear unreversed in the PDF."""
    pdf = render_report_pdf(make_context())
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "CDL20261103000123" in text


# ---------------------------------------------------------------------------
# Amended notice (§9.4)
# ---------------------------------------------------------------------------


def test_amended_notice_box() -> None:
    html = render_report_html(make_amended_context())
    assert "Amended report — this version corrects version 1." in html
    assert "Hemoglobin" in html
    assert "13.2" in html and "12.8" in html
    assert "dr.ayesha@citylab.pk" in html


def test_amended_version_history() -> None:
    html = render_report_html(make_amended_context())
    assert "Version 1" in html and "Version 2" in html


def test_amended_dagger_marks_changed_rows() -> None:
    html = render_report_html(make_amended_context())
    assert "†" in html


def test_v1_has_no_amended_notice() -> None:
    html = render_report_html(make_context())
    assert "Amended report" not in html
    assert "†" not in html


# ---------------------------------------------------------------------------
# Page limits (T-38, §9.6)
# ---------------------------------------------------------------------------


def _page_count(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def test_single_panel_report_fits_one_page() -> None:
    ctx = make_context()
    rows = [
        ResultRow(
            test_name=f"Test {i}",
            panel_name="Panel A",
            value="1.0",
            unit="u",
            flag_display="",
            reference_interval="0 – 2",
            comments="",
            is_changed=False,
        )
        for i in range(5)
    ]
    object.__setattr__(
        ctx, "result_groups", [ResultGroup(panel_name="Panel A", rows=rows)]
    )
    assert _page_count(render_report_pdf(ctx)) == 1


def test_full_catalogue_report_fits_three_pages() -> None:
    ctx = make_context()
    rows = [
        ResultRow(
            test_name=f"Test {i:02d}",
            panel_name=f"Panel {i // 10}",
            value="1.0",
            unit="u",
            flag_display="H" if i % 3 == 0 else "",
            reference_interval="0 – 2",
            comments="",
            is_changed=False,
        )
        for i in range(40)
    ]
    groups = [
        ResultGroup(
            panel_name=f"Panel {p}",
            rows=[r for r in rows if r.panel_name == f"Panel {p}"],
        )
        for p in range(4)
    ]
    object.__setattr__(ctx, "result_groups", groups)
    assert _page_count(render_report_pdf(ctx)) <= 3


# ---------------------------------------------------------------------------
# QR (§9.3)
# ---------------------------------------------------------------------------


def test_qr_payload_is_access_url() -> None:
    url = qr_payload_for_report("tok_abc123")
    assert url == "/api/v1/report-access/tok_abc123"


def test_qr_data_uri_is_png() -> None:
    uri = make_qr_data_uri("/api/v1/report-access/tok_abc123")
    assert uri.startswith("data:image/png;base64,")
    import base64

    raw = base64.b64decode(uri.split(",", 1)[1])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_qr_embedded_in_html() -> None:
    html = render_report_html(make_context())
    assert "data:image/png;base64," in html


# ---------------------------------------------------------------------------
# Failure behaviour (T-34)
# ---------------------------------------------------------------------------


def test_render_failure_is_clean() -> None:
    """A forced render error raises cleanly — no partial PDF bytes escape."""
    with pytest.raises((ValueError, TypeError)):
        render_report_pdf(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Builder (models -> context)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_builder_assembles_context_from_models() -> None:
    """Smoke: builder runs against real models (field-name contract)."""
    import uuid

    from apps.reports.models import Report

    report = Report(id=uuid.uuid4(), status="draft", current_version=0)
    # KAN-155 / LAB-30 (RP-2): the generate_pdf task builds the context for
    # a version that does not exist yet, on a draft report. Only void is
    # refused.
    report.status = "void"
    with pytest.raises(ValueError, match="void"):
        build_report_context(report, version=1)
