"""Model factories for apps.core public models."""

import uuid
from decimal import Decimal

import factory
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.core.models import (
    Domain,
    Plan,
    PlatformAudit,
    PlatformUser,
    Subscription,
    Tenant,
)
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


class PlatformUserFactory(PublicModelFactory[PlatformUser]):
    """Factory for PlatformUser public schema operator model (Doc 02 §4.1)."""

    class Meta:
        model = PlatformUser
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"admin{n}@labflow.app")
    password_hash = factory.LazyFunction(
        lambda: make_password("SuperAdminPassword123!")
    )
    totp_secret_encrypted = None
    totp_backup_codes_hash = None
    totp_enabled = False
    is_active = True


class PlatformAuditFactory(PublicModelFactory[PlatformAudit]):
    """Factory for PlatformAudit append-only public schema model (Doc 02 §4.1)."""

    class Meta:
        model = PlatformAudit

    actor_id = factory.LazyFunction(uuid.uuid4)
    action = "tenant.created"
    entity_type = "tenant"
    entity_id = factory.LazyFunction(uuid.uuid4)
    before_jsonb = None
    after_jsonb = factory.LazyFunction(lambda: {"status": "provisioning"})
    ip = "127.0.0.1"
    user_agent = "LabFlow-TestRunner/1.0"
