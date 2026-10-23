"""Scenario DG-01 skeleton test per Doc 09 §18.

Verbatim from Doc 09 §18:
Scenario: Open a PR with an unformatted Python file
Expected: Ruff format gate fails; merge blocked
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from django.db import connection
from django_tenants.utils import schema_context

from tests.fixtures.tenants import TenantFixture


@pytest.mark.dg
def test_dg01_ruff_format_gate_fails_on_unformatted_file(
    tenant_a: TenantFixture,
    tmp_path: Path,
) -> None:
    """
    DG-01: Verify Ruff format gate rejects unformatted Python code
    on the active harness.
    """
    # 1. Harness-level assertion: verify real PostgreSQL execution within tenant_a
    with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
        cursor.execute("SELECT current_schema();")
        current = cursor.fetchone()
        assert current is not None
        assert current[0] == tenant_a.schema_name

    # 2. Gate check: assert Ruff format check fails on unformatted code
    unformatted_file = tmp_path / "unformatted.py"
    unformatted_file.write_text("def   unformatted( x,y ):\n  return x+y\n")

    res_fail = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", str(unformatted_file)],
        capture_output=True,
        text=True,
    )
    assert res_fail.returncode != 0
    fail_output = res_fail.stdout + res_fail.stderr
    assert (
        "would be reformatted" in fail_output.lower()
        or "reformat" in fail_output.lower()
    )

    # 3. Verify compliant file passes format check
    formatted_file = tmp_path / "formatted.py"
    formatted_file.write_text(
        '"""Compliant module."""\n\n\n'
        "def add(x: int, y: int) -> int:\n"
        "    return x + y\n"
    )

    res_pass = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", str(formatted_file)],
        capture_output=True,
        text=True,
    )
    assert res_pass.returncode == 0

    # Full CI PR gate and merge blocking in GitHub Actions is completed in LAB-15.
