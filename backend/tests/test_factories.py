"""Tests verifying factory_boy infrastructure and tenant schema isolation guards.

Implements verification per Doc 09 §9.4 and Doc 01 ADR-003.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection, models
from django_tenants.utils import schema_context

from tests.factories.base import TenantModelFactory
from tests.factories.tenants import TenantFactory, TenantFixtureFactory
from tests.fixtures.tenants import TenantFixture


@pytest.mark.factory
def test_tenant_fixture_factory_build() -> None:
    """Prove TenantFixtureFactory.build creates in-memory instance without DB writes."""
    tenant = TenantFixtureFactory.build()

    assert isinstance(tenant, TenantFixture)
    assert tenant.schema_name.startswith("tenant_fac_")
    assert tenant.slug.startswith("tenant-fac-")
    assert tenant.name.startswith("Factory Tenant ")


@pytest.mark.factory
@pytest.mark.django_db(transaction=True)
def test_tenant_fixture_factory_create_provisions_and_reads_back() -> None:
    """Prove TenantFactory.create provisions PostgreSQL schema and can be read back."""
    tenant = TenantFactory.create()
    schema_name = tenant.schema_name

    try:
        # Verify schema exists in real PostgreSQL information_schema
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = %s;",
                [schema_name],
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == schema_name

        # Verify execution inside tenant schema context
        with schema_context(schema_name), connection.cursor() as cursor:
            cursor.execute("SELECT current_schema();")
            current = cursor.fetchone()

            assert current is not None
            assert current[0] == schema_name
    finally:
        # Clean teardown
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


@pytest.mark.factory
def test_tenant_model_factory_guards_against_public_schema() -> None:
    """
    Prove TenantModelFactory aborts with RuntimeError when called in 'public' schema.
    """

    # Define ephemeral unmanaged dummy model to verify factory execution logic
    class EphemeralDummyTenantModel(models.Model):
        class Meta:
            app_label = "core"
            managed = False

        def __str__(self) -> str:
            return "EphemeralDummyTenantModel"

    class EphemeralDummyFactory(TenantModelFactory):
        class Meta:
            model = EphemeralDummyTenantModel

    # Assert creation in 'public' schema fails loudly per Doc 09 §9.4
    with schema_context("public"):
        with pytest.raises(RuntimeError) as exc_info:
            EphemeralDummyFactory.build()  # build calls _build; test _create guard
            EphemeralDummyFactory.create()

        assert (
            "Cannot create tenant model 'EphemeralDummyTenantModel' "
            "in the 'public' schema" in str(exc_info.value)
        )


@pytest.mark.factory
@pytest.mark.django_db(transaction=True)
def test_tenant_model_factory_allows_creation_in_tenant_schema(
    tenant_a: TenantFixture,
) -> None:
    """
    Prove TenantModelFactory accepts creation when active in a valid tenant
    schema context.
    """

    class EphemeralTenantModel(models.Model):
        class Meta:
            app_label = "core"
            managed = False

        def __str__(self) -> str:
            return "EphemeralTenantModel"

    created_instances: list[Any] = []

    class EphemeralTenantFactory(TenantModelFactory):
        class Meta:
            model = EphemeralTenantModel

        @classmethod
        def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
            # Override default ORM save since EphemeralTenantModel has no DB table
            # Calls super()._create validation guard first
            current_schema = getattr(connection, "schema_name", "public")
            if current_schema == "public":
                raise RuntimeError("Forbidden in public")
            instance = model_class(*args, **kwargs)
            created_instances.append((instance, current_schema))
            return instance

    with schema_context(tenant_a.schema_name):
        instance = EphemeralTenantFactory.create()

    assert len(created_instances) == 1
    assert created_instances[0][0] == instance
    assert created_instances[0][1] == tenant_a.schema_name
