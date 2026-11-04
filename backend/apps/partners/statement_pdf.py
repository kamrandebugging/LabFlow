"""Statement PDF rendering (LAB-41 / KAN-260, Doc 05 §8.1–§8.4).

English-only template. WeasyPrint constraints per Doc 03 §9.5:
block layout, tables only, @page margin boxes, CSS counters for
"Page X of Y", no JavaScript, no web fonts at render time.
"""

from __future__ import annotations

import pathlib
from typing import Any

from django.template import Context, Template
from weasyprint import HTML  # type: ignore[import-untyped]

_TEMPLATE_PATH = pathlib.Path(__file__).parent / "templates" / "statement.html"


def _load_template() -> Template:
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))


def render_statement_html(ctx: dict[str, Any]) -> str:
    """Render the fixed statement template to an HTML string."""
    if not ctx:
        raise ValueError("Statement context is required")
    template = _load_template()
    return template.render(Context({"ctx": ctx}))


def render_statement_pdf(ctx: dict[str, Any]) -> bytes:
    """Render the statement to PDF bytes (A4).

    Raises cleanly on render failure — no partial PDF is ever returned
    (Doc 05 PDF-3: a failed attempt leaves the settlement APPROVED with
    statement_pdf_key still NULL, the visible retryable state).
    """
    html = render_statement_html(ctx)
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        raise
