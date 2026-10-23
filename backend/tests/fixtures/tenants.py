"""Shared two-tenant isolation fixtures (Doc 09 §9.4).

Provides tenant_a, tenant_b, and run_in_tenant helper fixtures using
real PostgreSQL schemas and django-tenants schema_context.
"""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any

import pytest
from django.db import connection
from django_tenants.utils import schema_context


@dataclass(frozen=True)
class TenantFixture:
    """Minimal tenant representation prior to LAB-5 Tenant model implementation."""

    schema_name: str
    slug: str
    name: str

    def schema_context(self) -> Any:
        """Context manager switching PostgreSQL search_path to this tenant schema."""
        return schema_context(self.schema_name)


def _provision_test_schema(schema_name: str) -> None:
    """Create a real PostgreSQL schema for testing."""
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')


def _drop_test_schema(schema_name: str) -> None:
    """Tear down the PostgreSQL test schema."""
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
    if hasattr(connection, "set_schema_to_public"):
        connection.set_schema_to_public()


@pytest.fixture
def tenant_a(db: Any) -> Generator[TenantFixture, None, None]:
    """Provision a real PostgreSQL schema for tenant_a and tear it down after test."""
    schema_name = "tenant_a"
    _provision_test_schema(schema_name)
    tenant = TenantFixture(schema_name=schema_name, slug="tenant_a", name="Tenant A")
    try:
        yield tenant
    finally:
        _drop_test_schema(schema_name)


@pytest.fixture
def tenant_b(db: Any) -> Generator[TenantFixture, None, None]:
    """Provision a real PostgreSQL schema for tenant_b and tear it down after test."""
    schema_name = "tenant_b"
    _provision_test_schema(schema_name)
    tenant = TenantFixture(schema_name=schema_name, slug="tenant_b", name="Tenant B")
    try:
        yield tenant
    finally:
        _drop_test_schema(schema_name)


@pytest.fixture
def run_in_tenant() -> Callable[..., Any]:
    """Paired helper fixture to run a callable inside a tenant's schema context."""

    def _runner(
        tenant: Any,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        schema = getattr(tenant, "schema_name", str(tenant))
        with schema_context(schema):
            return func(*args, **kwargs)

    return _runner


@pytest.fixture
def run_in_schema(run_in_tenant: Callable[..., Any]) -> Callable[..., Any]:
    """Alias for run_in_tenant fixture."""
    return run_in_tenant
