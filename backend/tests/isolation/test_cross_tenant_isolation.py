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
    """Doc 04 §13.7: Create instance in tenant_a, assert row invisible in tenant_b."""
    if tenant_model is None:
        pytest.skip("No tenant models registered yet")

    factory_cls = validate_tenant_model_factory(tenant_model)

    # 1. Create instance within tenant_a schema context
    with schema_context(tenant_a.schema_name):
        instance: Any = factory_cls.create()
        record_id = instance.pk
        assert tenant_model._default_manager.filter(pk=record_id).exists() is True

    # 2. Query within tenant_b schema context and assert record is strictly invisible
    with schema_context(tenant_b.schema_name):
        assert tenant_model._default_manager.filter(pk=record_id).exists() is False
        assert tenant_model._default_manager.filter(pk=record_id).count() == 0
