"""Base model factories for tenant and public schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import factory
from django.db import connection, models
from django_tenants.utils import schema_context
from factory.django import DjangoModelFactory


class TenantModelFactory[T: models.Model](DjangoModelFactory[T]):
    """Base factory for tenant-scoped models.

    Guarantees that model creation executes inside an active tenant schema context.
    Prevents silent cross-tenant data leakage or accidental writes to the 'public'
    schema per Doc 01 §8 and Doc 09 §9.4.
    """

    class Meta:
        abstract = True

    if TYPE_CHECKING:

        def __new__(cls, *args: Any, **kwargs: Any) -> Any: ...

        @classmethod
        def build(cls, **kwargs: Any) -> Any: ...

        @classmethod
        def create(cls, **kwargs: Any) -> Any: ...

    @classmethod
    def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
        explicit_schema = kwargs.pop("_schema", None)
        if explicit_schema is None:
            tenant_arg = kwargs.pop("_tenant", None)
            if tenant_arg is not None:
                explicit_schema = getattr(tenant_arg, "schema_name", str(tenant_arg))

        if explicit_schema:
            with schema_context(explicit_schema):
                return super()._create(model_class, *args, **kwargs)

        current_schema = getattr(connection, "schema_name", "public")
        if current_schema == "public":
            raise RuntimeError(
                f"Cannot create tenant model '{model_class.__name__}' "
                "in the 'public' schema. Tenant models must be created within an "
                "active tenant schema context (e.g. inside run_in_tenant, "
                "schema_context, or passing _schema/_tenant) "
                "per Doc 01 ADR-003 and Doc 09 §9.4."
            )
        return super()._create(model_class, *args, **kwargs)


class PublicModelFactory[T: models.Model](DjangoModelFactory[T]):
    """Base factory for public-schema models (Tenant, Domain, Plan, PlatformUser).

    Guarantees that creation executes strictly within the 'public' schema context.
    """

    class Meta:
        abstract = True

    if TYPE_CHECKING:

        def __new__(cls, *args: Any, **kwargs: Any) -> Any: ...

        @classmethod
        def build(cls, **kwargs: Any) -> Any: ...

        @classmethod
        def create(cls, **kwargs: Any) -> Any: ...

    @classmethod
    def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
        with schema_context("public"):
            return super()._create(model_class, *args, **kwargs)


class BaseTenantFixtureFactory(factory.Factory[Any]):
    """Base factory for test harness tenant records (e.g. TenantFixture).

    Abstract factory for non-ORM tenant representations used in testing.
    """

    class Meta:
        abstract = True
