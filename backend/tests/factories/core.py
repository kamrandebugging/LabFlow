"""Model factories for apps.core public models."""

import factory

from apps.core.models import Domain, Tenant
from tests.factories.base import PublicModelFactory


class TenantFactory(PublicModelFactory[Tenant]):
    """Factory for Tenant public schema model."""

    class Meta:
        model = Tenant
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"lab{n}")
    name = factory.Sequence(lambda n: f"Diagnostic Lab {n}")
    schema_name = factory.LazyAttribute(lambda o: f"tenant_{o.slug}")
    status = Tenant.Status.ACTIVE


class DomainFactory(PublicModelFactory[Domain]):
    """Factory for Domain public schema model."""

    class Meta:
        model = Domain
        django_get_or_create = ("domain",)

    domain = factory.Sequence(lambda n: f"lab{n}.localhost")
    tenant = factory.SubFactory(TenantFactory)
    is_primary = True
