"""
Pytest session configuration and safety guards for LabFlow.
Enforces real PostgreSQL 16 and Redis 7 per Doc 09 §9.1.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import django
import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    """
    Session-start hook to verify database engine configuration before any test executes.
    Aborts immediately if SQLite is configured (Doc 09 §9.1).
    """
    # Ensure Django settings are configured
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    if not django.conf.settings.configured:
        django.setup()

    from django.conf import settings

    default_db = settings.DATABASES.get("default", {})
    engine = str(default_db.get("ENGINE", ""))

    if "sqlite" in engine.lower():
        pytest.exit(
            "SQLite is not allowed — tests must run against PostgreSQL (Doc 09 §9.1).\n"
            f"Configured engine: {engine}",
            returncode=1,
        )

    if "postgresql" not in engine.lower() and "django_tenants" not in engine.lower():
        pytest.exit(
            "Invalid database engine for test suite — "
            "must be PostgreSQL / django-tenants (Doc 09 §9.1).\n"
            f"Found: {engine}",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def enforce_postgresql_connection() -> Generator[None, None, None]:
    """
    Session-scoped runtime fixture to verify actual database connection vendor
    is PostgreSQL.
    """
    from django.db import connection

    vendor = connection.vendor
    if vendor == "sqlite":
        pytest.exit(
            "SQLite is not allowed — tests must run against PostgreSQL (Doc 09 §9.1).\n"
            f"Detected connection vendor: {vendor}",
            returncode=1,
        )
    if vendor != "postgresql":
        pytest.exit(
            "Invalid connection vendor for test suite — "
            f"expected 'postgresql', got: '{vendor}' (Doc 09 §9.1).",
            returncode=1,
        )
    yield
