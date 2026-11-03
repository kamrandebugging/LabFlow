"""Automated cross-tenant isolation test suite per Doc 04 §13.7.

Dynamically parameterized from the model registry:
1. Creates instance inside tenant_a using its <Model>Factory.
2. Asserts record is invisible inside tenant_b schema.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import models
from django_tenants.utils import schema_context

from tests.fixtures.tenants import TenantFixture
from tests.isolation.generator import (
    get_tenant_models,
    is_model_excluded,
    validate_tenant_model_factory,
)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate dynamic test cases for each tenant model in settings.TENANT_APPS."""
    if "tenant_model" in metafunc.fixturenames:
        registered_models = get_tenant_models()

        # Filter out excluded models while honoring the failure contract
        active_models: list[type[models.Model]] = []
        for model in registered_models:
            excluded, _ = is_model_excluded(model)
            if not excluded:
                # Validate that factory exists immediately at collection time
                validate_tenant_model_factory(model)
                active_models.append(model)

        if not active_models:
            # LAB-4 baseline: No domain models exist until LAB-5
            metafunc.parametrize(
                "tenant_model",
                [
                    pytest.param(
                        None,
                        marks=pytest.mark.skip(
                            reason=(
                                "No unexcluded tenant models registered in "
                                "TENANT_APPS at LAB-4 (domain models start at LAB-5)"
                            )
                        ),
                    )
                ],
                ids=["no_tenant_models_at_lab_4"],
            )
        else:
            metafunc.parametrize(
                "tenant_model",
                active_models,
                ids=[f"{m._meta.app_label}.{m.__name__}" for m in active_models],
            )


@pytest.mark.isolation
@pytest.mark.tenancy
def test_tenant_model_cross_tenant_isolation(
    tenant_model: type[models.Model] | None,
    tenant_a: TenantFixture,
    tenant_b: TenantFixture,
) -> None:
    """Doc 04 §13.7 / TN-31: one factory row per tenant; full isolation.

    - A's row ID on B's host (schema) -> 404-equivalent: strictly invisible.
    - B's lists never contain A's key.
    - A B-context query returns only B's row.
    """
    if tenant_model is None:
        pytest.skip("No tenant models registered yet")

    factory_cls = validate_tenant_model_factory(tenant_model)

    # 1. One factory row in each tenant schema.
    with schema_context(tenant_a.schema_name):
        row_a: Any = factory_cls.create()
        id_a = row_a.pk
        assert tenant_model._default_manager.filter(pk=id_a).exists() is True
    with schema_context(tenant_b.schema_name):
        row_b: Any = factory_cls.create()
        id_b = row_b.pk
        assert tenant_model._default_manager.filter(pk=id_b).exists() is True

    # 2. A's row ID is strictly invisible inside B's schema (404-equivalent).
    with schema_context(tenant_b.schema_name):
        assert tenant_model._default_manager.filter(pk=id_a).exists() is False
        assert tenant_model._default_manager.filter(pk=id_a).count() == 0

    # 3. B's lists never contain A's key; a B-context query returns only B.
    with schema_context(tenant_b.schema_name):
        listed_ids = set(tenant_model._default_manager.values_list("pk", flat=True))
        assert id_b in listed_ids
        assert id_a not in listed_ids

    # 4. Symmetry: B's row is invisible inside A's schema.
    with schema_context(tenant_a.schema_name):
        assert tenant_model._default_manager.filter(pk=id_b).exists() is False
        listed_ids_a = set(tenant_model._default_manager.values_list("pk", flat=True))
        assert id_a in listed_ids_a
        assert id_b not in listed_ids_a
