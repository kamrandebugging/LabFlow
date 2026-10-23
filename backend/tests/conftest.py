"""Pytest root configuration and environment sanity checks (Doc 09 §9.1)."""

from typing import Any

import pytest
from django.conf import settings
from django.db import connection

# Re-export two-tenant fixtures and helpers per Doc 09 §9.4
from tests.fixtures.tenants import (
    TenantFixture,
    run_in_schema,
    run_in_tenant,
    tenant_a,
    tenant_b,
)

__all__ = [
    "TenantFixture",
    "run_in_schema",
    "run_in_tenant",
    "tenant_a",
    "tenant_b",
]


def pytest_sessionstart(session: pytest.Session) -> None:
    """
    Abort pytest session immediately if SQLite or non-PostgreSQL backend is configured.
    """
    import os

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    if not settings.configured:
        django.setup()

    engine = str(settings.DATABASES["default"]["ENGINE"])
    allowed_backends = (
        "django.db.backends.postgresql",
        "django_tenants.postgresql_backend",
    )
    if "sqlite" in engine or not any(backend in engine for backend in allowed_backends):
        pytest.exit(
            "SQLite is not allowed — tests must run against PostgreSQL (Doc 09 §9.1). "
            f"Configured engine: {engine}",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def enforce_postgresql_connection(django_db_blocker: Any) -> None:
    """Verify live database connection vendor is postgresql at session start."""
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
        if connection.vendor != "postgresql":
            pytest.fail(
                "Expected database connection vendor 'postgresql', "
                f"got '{connection.vendor}'. "
                "SQLite fallback strictly prohibited per Doc 09 §9.1."
            )
