"""Phase 0 gate: render the repo's golden report fixture with the bundled fonts.

Run inside the backend image:
    docker run --rm -v <repo>/backend:/src -v <repo>/artifacts/phase0:/out \
        -w /src labflow-backend:urdu-phase0 python scripts/phase0_render.py

This is the project's deterministic PDF fixture (tests/tenancy/
test_lab29_report_pdf.py), not invented data: it exercises the real render
boundary and the exact Urdu block the patient sees.
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
os.environ.setdefault("DJANGO_SECRET_KEY", "phase0-proof-secret-key-32-chars-minimum")

import django  # noqa: E402

django.setup()

from apps.reports.pdf.rendering import render_report_pdf  # noqa: E402
from tests.tenancy.test_lab29_report_pdf import make_context  # noqa: E402

OUT = pathlib.Path("/out")
OUT.mkdir(parents=True, exist_ok=True)
pdf = render_report_pdf(make_context())
target = OUT / "phase0-report.pdf"
target.write_bytes(pdf)
print(f"wrote {target} ({len(pdf)} bytes)")
