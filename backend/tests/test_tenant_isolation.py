"""Unit & Integration tests for two-tenant fixture and schema isolation.

Conforms to Doc 09 §9.4.
"""

from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django_tenants.utils import schema_context

from tests.fixtures.tenants import TenantFixture


@pytest.mark.django_db(transaction=True)
def test_tenant_fixtures_provision_real_schemas(
    tenant_a: TenantFixture,
    tenant_b: TenantFixture,
) -> None:
    """Verify that tenant_a and tenant_b provision real schemas in PostgreSQL."""
    assert tenant_a.schema_name == "tenant_a"
    assert tenant_b.schema_name == "tenant_b"

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name IN ('tenant_a', 'tenant_b')
            ORDER BY schema_name;
            """
        )
        existing_schemas = [row[0] for row in cursor.fetchall()]

    assert existing_schemas == ["tenant_a", "tenant_b"]


@pytest.mark.django_db(transaction=True)
def test_schema_context_switches_search_path(
    tenant_a: TenantFixture,
    tenant_b: TenantFixture,
) -> None:
    """Verify that schema_context properly switches search_path without manual SET."""
    with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
        cursor.execute("SHOW search_path;")
        row = cursor.fetchone()
        assert row is not None
        path_a = str(row[0])
        assert "tenant_a" in path_a
        assert "tenant_b" not in path_a

    with schema_context(tenant_b.schema_name), connection.cursor() as cursor:
        cursor.execute("SHOW search_path;")
        row = cursor.fetchone()
        assert row is not None
        path_b = str(row[0])
        assert "tenant_b" in path_b
        assert "tenant_a" not in path_b


@pytest.mark.django_db(transaction=True)
def test_run_in_tenant_helper_executes_in_correct_schema(
    tenant_a: TenantFixture,
    tenant_b: TenantFixture,
    run_in_tenant: Callable[..., Any],
) -> None:
    """Verify run_in_tenant executes callables inside the specified tenant schema."""

    def get_current_search_path() -> str:
        with connection.cursor() as cursor:
            cursor.execute("SHOW search_path;")
            row = cursor.fetchone()
            assert row is not None
            return str(row[0])

    path_a = run_in_tenant(tenant_a, get_current_search_path)
    path_b = run_in_tenant(tenant_b, get_current_search_path)

    assert "tenant_a" in path_a
    assert "tenant_b" in path_b


@pytest.mark.django_db(transaction=True)
def test_cross_tenant_data_isolation(
    tenant_a: TenantFixture,
    tenant_b: TenantFixture,
    run_in_tenant: Callable[..., Any],
) -> None:
    """
    Verify that table rows created in tenant_a are completely invisible in tenant_b.
    """

    def create_and_populate_table() -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE test_record (
                    id SERIAL PRIMARY KEY,
                    data VARCHAR(100)
                );
                INSERT INTO test_record (data) VALUES ('tenant_a_secret_data');
                """
            )

    def check_table_in_tenant_b() -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'tenant_b' AND table_name = 'test_record'
                );
                """
            )
            row = cursor.fetchone()
            assert row is not None
            return bool(row[0])

    run_in_tenant(tenant_a, create_and_populate_table)
    table_exists_in_b = run_in_tenant(tenant_b, check_table_in_tenant_b)

    assert table_exists_in_b is False


@pytest.mark.django_db(transaction=True)
def test_teardown_cleans_up_schemas(db: Any) -> None:
    """Verify that schema teardown drops tenant schemas after test completion."""
    from tests.fixtures.tenants import _drop_test_schema, _provision_test_schema

    temp_schema = "tenant_temp_check"
    _provision_test_schema(temp_schema)

    check_sql = "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s"
    with connection.cursor() as cursor:
        cursor.execute(check_sql, [temp_schema])
        assert cursor.fetchone() is not None

    _drop_test_schema(temp_schema)

    with connection.cursor() as cursor:
        cursor.execute(check_sql, [temp_schema])
        assert cursor.fetchone() is None
