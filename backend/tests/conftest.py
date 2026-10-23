"""Pytest root fixtures and session configuration."""

from collections.abc import Generator
from typing import Any

import pytest
from django.db import connection

from apps.core.models import Domain, Tenant


@pytest.fixture(autouse=True, scope="session")
def enforce_no_sqlite(django_db_setup: Any) -> None:
    """Disallow SQLite execution per Doc 09 §9.1."""
    vendor = connection.vendor
    if vendor != "postgresql":
        pytest.exit(
            (
                f"CRITICAL: Test execution on vendor '{vendor}' forbidden. "
                "Real PostgreSQL 16 required."
            ),
            returncode=1,
        )


@pytest.fixture
def tenant_a(db: Any) -> Generator[Tenant, None, None]:
    """Primary test tenant fixture backed by real Tenant model."""
    tenant, _ = Tenant.objects.get_or_create(
        schema_name="tenant_a",
        defaults={
            "name": "Tenant A",
            "slug": "tenant_a",
            "status": Tenant.Status.ACTIVE,
        },
    )
    Domain.objects.get_or_create(
        tenant=tenant,
        domain="tenant-a.localhost",
        defaults={"is_primary": True},
    )
    yield tenant
    Domain.objects.filter(tenant=tenant).delete()
    tenant.delete(force_drop=True)


@pytest.fixture
def tenant_b(db: Any) -> Generator[Tenant, None, None]:
    """Secondary test tenant fixture for cross-tenant isolation testing."""
    tenant, _ = Tenant.objects.get_or_create(
        schema_name="tenant_b",
        defaults={
            "name": "Tenant B",
            "slug": "tenant_b",
            "status": Tenant.Status.ACTIVE,
        },
    )
    Domain.objects.get_or_create(
        tenant=tenant,
        domain="tenant-b.localhost",
        defaults={"is_primary": True},
    )
    yield tenant
    Domain.objects.filter(tenant=tenant).delete()
    tenant.delete(force_drop=True)
