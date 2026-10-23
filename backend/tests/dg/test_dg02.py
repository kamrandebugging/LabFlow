"""Scenario DG-02 skeleton test per Doc 09 §18.

Verbatim from Doc 09 §18:
Scenario: Open a PR with an untyped service function
Expected: mypy gate fails with the function named
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from django.core.cache import cache
from django.db import connection
from django_tenants.utils import schema_context

from tests.fixtures.tenants import TenantFixture


@pytest.mark.dg
def test_dg02_mypy_gate_fails_with_function_named(
    tenant_a: TenantFixture,
    tmp_path: Path,
) -> None:
    """DG-02: Verify Mypy rejects untyped service functions and names the function."""
    # 1. Harness-level assertion: verify real PostgreSQL and Redis execution
    with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS active;")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1
    cache.set(f"dg02_{tenant_a.slug}", "active", timeout=10)
    assert cache.get(f"dg02_{tenant_a.slug}") == "active"

    # 2. Gate check: assert mypy rejects function missing parameter
    # and return annotations
    untyped_service_file = tmp_path / "untyped_service.py"
    untyped_service_file.write_text(
        "def execute_payment_service(invoice_id, amount):\n    return amount * 2\n"
    )

    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            "pyproject.toml",
            "--disallow-untyped-defs",
            "--pretty",
            str(untyped_service_file),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    output = res.stdout + res.stderr
    assert "execute_payment_service" in output
    assert "Function is missing a type annotation" in output

    # Full CI PR gate and merge blocking in GitHub Actions is completed in LAB-15.
