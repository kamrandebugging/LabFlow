"""Unit tests proving the cross-tenant harness generator logic per Doc 04 §13.7."""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.db import connection, models
from django_tenants.utils import schema_context

from tests.factories.base import TenantModelFactory
from tests.fixtures.tenants import TenantFixture
from tests.isolation.generator import (
    EXCLUDED_MODELS,
    get_tenant_app_labels,
    get_tenant_models,
    is_model_excluded,
    validate_tenant_model_factory,
)


@pytest.mark.isolation
def test_get_tenant_app_labels_matches_settings() -> None:
    """Prove get_tenant_app_labels extracts all apps defined in settings.TENANT_APPS."""
    labels = get_tenant_app_labels()
    configured_apps = getattr(settings, "TENANT_APPS", [])

    assert len(labels) == len(configured_apps)
    for app in configured_apps:
        expected_label = app.split(".")[-1]
        assert expected_label in labels


@pytest.mark.isolation
def test_get_tenant_models_is_o_m() -> None:
    """Prove get_tenant_models executes cleanly and returns a list of model classes."""
    models_list = get_tenant_models()
    assert isinstance(models_list, list)


@pytest.mark.isolation
def test_missing_factory_fails_loudly_naming_model() -> None:
    """Prove missing factory raises RuntimeError naming the exact un-factored model."""

    class UnfactoredTenantModel(models.Model):
        class Meta:
            app_label = "core"
            managed = False

        def __str__(self) -> str:
            return "UnfactoredTenantModel"

    with pytest.raises(RuntimeError) as exc_info:
        validate_tenant_model_factory(UnfactoredTenantModel)

    err_msg = str(exc_info.value)
    assert "Missing factory for tenant model 'core.UnfactoredTenantModel'" in err_msg
    assert "Expected factory named 'UnfactoredTenantModelFactory'" in err_msg
    assert "review blocker" in err_msg


@pytest.mark.isolation
def test_excluded_models_check() -> None:
    """Prove is_model_excluded detects documented exclusions."""

    class MockModel(models.Model):
        class Meta:
            app_label = "core"
            managed = False

        def __str__(self) -> str:
            return "MockModel"

    model_key = f"{MockModel._meta.app_label}.{MockModel.__name__}"
    EXCLUDED_MODELS[model_key] = "Hardware driver dependency"

    try:
        excluded, reason = is_model_excluded(MockModel)
        assert excluded is True
        assert reason == "Hardware driver dependency"

        with pytest.raises(ValueError) as exc_info:
            validate_tenant_model_factory(MockModel)
        assert "Hardware driver dependency" in str(exc_info.value)
    finally:
        EXCLUDED_MODELS.pop(model_key, None)


@pytest.mark.isolation
@pytest.mark.tenancy
def test_generator_synthetic_isolation_flow(
    tenant_a: TenantFixture,
    tenant_b: TenantFixture,
) -> None:
    """Prove generator isolation verification flow against real PostgreSQL schemas."""

    table_name = "test_synthetic_harness_model"

    # Provision ephemeral table in both schemas
    create_sql = (
        f'CREATE TABLE IF NOT EXISTS "{table_name}" (id serial PRIMARY KEY, name text);'
    )
    with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
        cursor.execute(create_sql)

    with schema_context(tenant_b.schema_name), connection.cursor() as cursor:
        cursor.execute(create_sql)

    try:
        # Ephemeral model mapped to table_name
        class SyntheticTenantModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "core"
                db_table = table_name
                managed = False

            def __str__(self) -> str:
                return str(self.name)

        class SyntheticTenantModelFactory(TenantModelFactory):
            class Meta:
                model = SyntheticTenantModel

            name = "Isolated Entity"

            @classmethod
            def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
                name = kwargs.get("name", "Isolated Entity")
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'INSERT INTO "{table_name}" (name) VALUES (%s) RETURNING id;',
                        [name],
                    )
                    row = cursor.fetchone()
                    assert row is not None
                    instance = model_class(id=row[0], name=name)
                    return instance

        # 1. Insert in tenant_a
        with schema_context(tenant_a.schema_name):
            created = SyntheticTenantModelFactory.create(name="Tenant A Secret")

        with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
            cursor.execute(
                f'SELECT COUNT(*) FROM "{table_name}" WHERE id = %s;', [created.id]
            )
            row_a = cursor.fetchone()
            assert row_a is not None
            assert row_a[0] == 1

        # 2. Query in tenant_b -> Must be invisible (0 rows)
        with schema_context(tenant_b.schema_name), connection.cursor() as cursor:
            cursor.execute(
                f'SELECT COUNT(*) FROM "{table_name}" WHERE id = %s;', [created.id]
            )
            row_b = cursor.fetchone()
            assert row_b is not None
            assert row_b[0] == 0

    finally:
        with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
        with schema_context(tenant_b.schema_name), connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
