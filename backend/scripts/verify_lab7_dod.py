"""Standalone verification runner for Story KAN-44 (LAB-7) Definition of Done.

Executes pytest on test_lab7_definition_of_done.py, test_lab7_subtask*.py,
and tests/isolation/, plus pytest --collect-only for the 22 LAB-7 models.
"""

from __future__ import annotations

import subprocess
import sys


def run_step(title: str, cmd: list[str]) -> None:
    print(f"\n{'=' * 72}")
    print(f"[LAB-7 DoD] {title}")
    print(f"$ {' '.join(cmd)}")
    print(f"{'=' * 72}")
    result = subprocess.run(cmd, text=True, check=False)
    if result.returncode != 0:
        print(f"\n[FAIL] {title} exited with code {result.returncode}")
        sys.exit(result.returncode)
    print(f"[PASS] {title}")


def main() -> None:
    run_step(
        "Check 1a: Zero Migration Drift (makemigrations --check --dry-run)",
        [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
    )
    run_step(
        "Check 1b: Shared & Tenant Schema Migrations",
        [sys.executable, "manage.py", "migrate_schemas", "--shared"],
    )
    run_step(
        "Check 1c: Tenant Schema Migrations",
        [sys.executable, "manage.py", "migrate_schemas", "--tenant"],
    )
    run_step(
        "Check 7a: Isolation Collection (--collect-only for all 22 LAB-7 models)",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/isolation/test_cross_tenant_isolation.py",
            "--collect-only",
            "-q",
        ],
    )
    run_step(
        ("Checks 1-8: Full LAB-7 DoD, Subtasks 1-9, and Cross-Tenant Isolation Suite"),
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/tenancy/test_lab7_definition_of_done.py",
            "tests/tenancy/test_lab7_subtask1_patients.py",
            "tests/tenancy/test_lab7_subtask2_catalog.py",
            "tests/tenancy/test_lab7_subtask3_reference_range.py",
            "tests/tenancy/test_lab7_subtask4_billing.py",
            "tests/tenancy/test_lab7_subtask5_payment.py",
            "tests/tenancy/test_lab7_subtask6_samples.py",
            "tests/tenancy/test_lab7_subtask7_results.py",
            "tests/tenancy/test_lab7_subtask8_reports.py",
            "tests/tenancy/test_lab7_subtask9_revoke_and_dod.py",
            "tests/isolation/",
            "-v",
        ],
    )
    print("\nALL 8 LAB-7 DEFINITION OF DONE CHECKS PASSED (EXIT CODE 0).")


if __name__ == "__main__":
    main()
