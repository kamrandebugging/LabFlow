"""Base factory classes for LabFlow per Doc 09 §9.4 and Doc 01 ADR-003.

Enforces schema context boundaries for tenant and public models.
"""

from __future__ import annotations

from typing import Any

import factory
from django.db import connection
from django_tenants.utils import schema_context


class TenantModelFactory(factory.django.DjangoModelFactory):
    """Base factory for tenant-scoped models.

    Guarantees that model creation executes inside an active tenant schema context.
    Prevents silent cross-tenant data leakage or accidental writes to the 'public'
    schema per Doc 01 §8 and Doc 09 §9.4.
    """

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
        # Check for explicit schema override parameters
        explicit_schema = kwargs.pop("_schema", None)
        if explicit_schema is None:
            tenant_arg = kwargs.pop("_tenant", None)
            if tenant_arg is not None:
                explicit_schema = getattr(tenant_arg, "schema_name", str(tenant_arg))

        if explicit_schema:
            with schema_context(explicit_schema):
                return super()._create(model_class, *args, **kwargs)

        # Enforce that current connection schema is not 'public'
        current_schema = getattr(connection, "schema_name", "public")
        if current_schema == "public":
            raise RuntimeError(
                f"Cannot create tenant model '{model_class.__name__}' in the 'public' "
                f"schema. Tenant models must be created within an active tenant "
                f"schema context (e.g. inside run_in_tenant, schema_context, or "
                f"passing _schema/_tenant) per Doc 01 ADR-003 and Doc 09 §9.4."
            )

        return super()._create(model_class, *args, **kwargs)


class PublicModelFactory(factory.django.DjangoModelFactory):
    """Base factory for public-schema models (Tenant, Domain, Plan, PlatformUser).

    Guarantees that creation executes strictly within the 'public' schema context.
    """

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
        with schema_context("public"):
            return super()._create(model_class, *args, **kwargs)


class BaseTenantFixtureFactory(factory.Factory):
    """Base factory for test harness tenant records (e.g. TenantFixture).

    Abstract factory for non-ORM tenant representations used in testing.
    """

    class Meta:
        abstract = True
