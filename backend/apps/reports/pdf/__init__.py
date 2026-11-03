"""LAB-29 (KAN-154): report PDF package."""

from .builder import build_report_context
from .rendering import render_report_html, render_report_pdf

__all__ = ["build_report_context", "render_report_html", "render_report_pdf"]
