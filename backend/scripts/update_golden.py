"""Regenerate the LAB-29 golden HTML after a template change."""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
os.environ.setdefault("DJANGO_SECRET_KEY", "golden-update-secret-key-32-chars-min")

import django  # noqa: E402

django.setup()

from apps.reports.pdf.rendering import render_report_html  # noqa: E402
from tests.tenancy.test_lab29_report_pdf import make_context  # noqa: E402

target = pathlib.Path(__file__).resolve().parents[1] / "tests/tenancy/golden/lab29_report_v1.html"
target.write_text(render_report_html(make_context()), encoding="utf-8")
print("wrote", target)
