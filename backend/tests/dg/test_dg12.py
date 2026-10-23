"""Scenario DG-12 skeleton test per Doc 09 §18.

Verbatim from Doc 09 §18:
Scenario: Delete a test so line coverage falls
Expected: Ratchet gate fails against main (§9.3)
"""

from __future__ import annotations

import pytest
from django.db import connection
from django_tenants.utils import schema_context

from tests.fixtures.tenants import TenantFixture


def evaluate_coverage_ratchet(
    current_coverage: float, baseline_coverage: float
) -> bool:
    """
    Evaluate coverage ratchet per Doc 09 §9.3: coverage must not fall versus baseline.
    """
    if current_coverage < baseline_coverage:
        raise AssertionError(
            f"Coverage ratchet failed: current coverage ({current_coverage:.2f}%) "
            f"is below baseline ({baseline_coverage:.2f}%) per Doc 09 §9.3."
        )
    return True


@pytest.mark.dg
def test_dg12_coverage_ratchet_gate_fails_when_coverage_drops(
    tenant_a: TenantFixture,
) -> None:
    """
    DG-12: Verify coverage ratchet gate rejects coverage decreases
    per Doc 09 §9.3.
    """
    # 1. Harness-level assertion: verify real PostgreSQL execution
    with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
        cursor.execute("SELECT current_schema();")
        current = cursor.fetchone()
        assert current is not None
        assert current[0] == tenant_a.schema_name

    # 2. Gate check: higher or equal coverage passes ratchet
    assert (
        evaluate_coverage_ratchet(current_coverage=85.50, baseline_coverage=85.00)
        is True
    )
    assert (
        evaluate_coverage_ratchet(current_coverage=85.00, baseline_coverage=85.00)
        is True
    )

    # 3. Gate check: dropped coverage fails loudly with AssertionError
    with pytest.raises(AssertionError) as exc_info:
        evaluate_coverage_ratchet(current_coverage=84.99, baseline_coverage=85.00)

    err = str(exc_info.value)
    assert "Coverage ratchet failed" in err
    assert "below baseline" in err
    assert "Doc 09 §9.3" in err

    # Full CI comparison against previous merge to main in GitHub Actions
    # is completed in LAB-15.
