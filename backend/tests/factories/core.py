"""Model factories for apps.core public models."""

from decimal import Decimal

import factory
from django.utils import timezone

from apps.core.models import Domain, Plan, Subscription, Tenant
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


class PlanFactory(PublicModelFactory[Plan]):
    """Factory for Plan public schema model (Doc 02 §4.1)."""

    class Meta:
        model = Plan
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Tier {n}")
    price = Decimal("5000.00")
    max_branches = None
    is_active = True


class SubscriptionFactory(PublicModelFactory[Subscription]):
    """Factory for Subscription public schema model (Doc 02 §4.1)."""

    class Meta:
        model = Subscription

    tenant = factory.SubFactory(TenantFactory)
    plan = factory.SubFactory(PlanFactory)
    status = Subscription.Status.ACTIVE
    starts_at = factory.LazyFunction(timezone.now)
    ends_at = None
