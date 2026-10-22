"""Baseline test harness validating test discovery and PostgreSQL configuration."""

import os
from decimal import Decimal


def test_harness_bootstrap() -> None:
    """Verify that the test suite is running under pytest."""
    assert True


def test_database_url_is_postgres() -> None:
    """Verify that SQLite fallback is prohibited per Doc 09 §9.1."""
    db_url = os.environ.get("DATABASE_URL", "")
    assert db_url.startswith("postgres://") or db_url.startswith("postgresql://"), (
        f"Prohibited database engine detected: {db_url}"
    )


def test_decimal_money_rule() -> None:
    """Verify standard money representation invariant (Doc 01 ADR-010, Doc 02 §2)."""
    amount = Decimal("1250.00")
    assert str(amount) == "1250.00"
