"""Factory for test harness tenant fixtures per Doc 09 §9.4."""

from __future__ import annotations

from typing import Any

import factory
from django.db import connection

from tests.factories.base import BaseTenantFixtureFactory
from tests.fixtures.tenants import TenantFixture


class TenantFixtureFactory(BaseTenantFixtureFactory):
    """Factory producing TenantFixture instances and provisioning PostgreSQL schemas."""

    class Meta:
        model = TenantFixture

    schema_name = factory.Sequence(lambda n: f"tenant_fac_{n}")
    slug = factory.Sequence(lambda n: f"tenant-fac-{n}")
    name = factory.Sequence(lambda n: f"Factory Tenant {n}")

    @classmethod
    def _create(
        cls, model_class: type[TenantFixture], *args: Any, **kwargs: Any
    ) -> TenantFixture:
        instance = model_class(*args, **kwargs)
        # Provision real PostgreSQL schema matching Subtask 2 fixture behavior
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{instance.schema_name}"')
        return instance


# Canonical alias adhering to the <Model>Factory naming convention
TenantFactory = TenantFixtureFactory
