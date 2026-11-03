"""
LAB-29 (KAN-154): WeasyPrint report rendering (§9.5).

Pure boundary: render_report_html/render_report_pdf take a plain-data
ReportContext and return str/bytes. No Django models, no Celery, no I/O
beyond the template file.

Intended Celery entry point (later LAB, reports queue):
    generate_pdf(report_id, version) -> render via ReportBuilder.build()
    then upload to the deterministic pdf_key and insert report_version
    (upload-then-insert ordering, §10). A render exception must fail the
    task cleanly with no partial PDF kept.
"""

from __future__ import annotations

import pathlib

from django.template import Context, Template
from weasyprint import HTML  # type: ignore[import-not-found,import-untyped]

from .context import ReportContext

_TEMPLATE_PATH = pathlib.Path(__file__).parent / "templates" / "report.html"


def _load_template() -> Template:
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))


def render_report_html(ctx: ReportContext) -> str:
    """Render the fixed report template to an HTML string."""
    if ctx is None:
        raise ValueError("ReportContext is required")
    template = _load_template()
    return template.render(Context({"ctx": ctx}))


def render_report_pdf(ctx: ReportContext) -> bytes:
    """
    Render the report to PDF bytes (A4, §9.5 constraints).

    Raises cleanly on render failure — no partial PDF is ever returned
    (T-34: a failed attempt leaves no report_version row; the caller,
    i.e. the future Celery task, must not write anything on exception).
    """
    html = render_report_html(ctx)  # raises ValueError on bad input
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        # Deliberately no partial bytes: WeasyPrint either returns the
        # complete document or raises.
        raise
