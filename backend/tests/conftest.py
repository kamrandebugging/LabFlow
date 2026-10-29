"""Pytest root configuration, environment sanity checks, and tenant fixtures.

Combines the LAB-4 harness guards (Doc 09 §9.1: SQLite hard-ban, live
PostgreSQL check, TenantFixture helpers re-exported from
tests.fixtures.tenants) with the LAB-5 tenant fixtures (KAN-38):
tenant_a / tenant_b are backed by the real Tenant model, keeping the
LAB-4 fixture names and interface stable.
"""

import contextlib
from collections.abc import Generator
from typing import Any

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection

from apps.core.models import Domain, Tenant

# Re-export harness helpers per Doc 09 §9.4 (fixtures defined in
# tests.fixtures.tenants register here; tenant_a/tenant_b are defined
# below on the real Tenant model per KAN-38 and are NOT imported).
from tests.fixtures.tenants import TenantFixture, run_in_schema, run_in_tenant

__all__ = [
    "TenantFixture",
    "run_in_schema",
    "run_in_tenant",
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


@pytest.fixture(autouse=True)
def purge_tenant_migrations_from_public(db: Any) -> None:
    """Ensure tenant app migrations recorded in public schema by test runner

    are purged.
    """
    tenant_apps = [app.split(".")[-1] for app in getattr(settings, "TENANT_APPS", ())]
    if tenant_apps:
        with connection.cursor() as cursor:
            placeholders = ", ".join(f"'{app}'" for app in tenant_apps)
            cursor.execute(
                f"DELETE FROM public.django_migrations WHERE app IN ({placeholders});"
            )


@pytest.fixture(autouse=True)
def public_tenant_domain(db: Any) -> None:
    """Ensure the public tenant and localhost domain exist for public routing."""
    public_tenant, _ = Tenant.objects.get_or_create(
        schema_name="public",
        defaults={
            "name": "LabFlow Platform",
            "slug": "public",
            "status": Tenant.Status.ACTIVE,
        },
    )
    Domain.objects.get_or_create(
        tenant=public_tenant,
        domain="localhost",
        defaults={"is_primary": True},
    )


@pytest.fixture
def tenant_a(db: Any) -> Generator[Tenant, None, None]:
    """Primary test tenant fixture backed by real Tenant model."""
    schema_name = "tenant_a"
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
    call_command("migrate_schemas", schema_name=schema_name, tenant=True, verbosity=0)
    tenant = Tenant(
        schema_name=schema_name,
        name="Tenant A",
        slug="tenant_a",
        status=Tenant.Status.ACTIVE,
    )
    tenant.auto_create_schema = False
    tenant.save()

    Domain.objects.get_or_create(
        tenant=tenant,
        domain="tenant-a.localhost",
        defaults={"is_primary": True},
    )
    yield tenant
    if connection.connection and not connection.connection.closed:
        with contextlib.suppress(Exception):
            connection.connection.rollback()
    connection.needs_rollback = False
    connection.rollback_exc = None
    if hasattr(connection, "set_schema_to_public"):
        connection.set_schema_to_public()
    Domain.objects.filter(tenant=tenant).delete()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
    tenant.auto_drop_schema = False
    tenant.delete()


@pytest.fixture
def tenant_b(db: Any) -> Generator[Tenant, None, None]:
    """Secondary test tenant fixture for cross-tenant isolation testing."""
    schema_name = "tenant_b"
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
    call_command("migrate_schemas", schema_name=schema_name, tenant=True, verbosity=0)
    tenant = Tenant(
        schema_name=schema_name,
        name="Tenant B",
        slug="tenant_b",
        status=Tenant.Status.ACTIVE,
    )
    tenant.auto_create_schema = False
    tenant.save()

    Domain.objects.get_or_create(
        tenant=tenant,
        domain="tenant-b.localhost",
        defaults={"is_primary": True},
    )
    yield tenant
    if connection.connection and not connection.connection.closed:
        with contextlib.suppress(Exception):
            connection.connection.rollback()
    connection.needs_rollback = False
    connection.rollback_exc = None
    if hasattr(connection, "set_schema_to_public"):
        connection.set_schema_to_public()
    Domain.objects.filter(tenant=tenant).delete()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
    tenant.auto_drop_schema = False
    tenant.delete()
