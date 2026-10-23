"""Tests for Plan and Subscription models and constraints (Doc 02 §4.1)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.core.models import Plan, Subscription
from tests.factories.core import PlanFactory, SubscriptionFactory, TenantFactory


@pytest.mark.django_db
def test_plan_creation_with_valid_price() -> None:
    """Plan creation succeeds with positive decimal price and default settings."""
    plan = Plan.objects.create(
        name="Standard Growth",
        price=Decimal("7500.00"),
        max_branches=3,
        is_active=True,
    )
    assert plan.id is not None
    assert plan.price == Decimal("7500.00")
    assert plan.max_branches == 3
    assert plan.is_active is True
    assert str(plan) == "Standard Growth (PKR 7500.00)"


@pytest.mark.django_db
def test_plan_negative_price_rejected_by_database() -> None:
    """PostgreSQL rejects negative plan price via chk_plan_price_gte_0 constraint."""
    with pytest.raises(IntegrityError):
        Plan.objects.create(
            name="Invalid Plan",
            price=Decimal("-100.00"),
        )


@pytest.mark.django_db
def test_subscription_creation_and_string_representation() -> None:
    """Subscription instantiates correctly with foreign keys and active status."""
    tenant = TenantFactory()
    plan = PlanFactory(name="Enterprise", price=Decimal("15000.00"))
    now = timezone.now()

    sub = Subscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now,
    )

    assert sub.id is not None
    assert sub.tenant == tenant
    assert sub.plan == plan
    assert sub.status == Subscription.Status.ACTIVE
    assert sub.ends_at is None
    assert str(sub) == f"{tenant.slug} -> Enterprise (active)"


@pytest.mark.django_db
def test_subscription_ends_at_check_constraint() -> None:
    """PostgreSQL rejects subscription where ends_at <= starts_at."""
    tenant = TenantFactory()
    plan = PlanFactory()
    now = timezone.now()

    with pytest.raises(IntegrityError):
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            starts_at=now,
            ends_at=now - timedelta(days=1),
        )


@pytest.mark.django_db
def test_subscription_one_active_per_tenant_enforced_by_database() -> None:
    """PostgreSQL rejects second active subscription for same tenant via
    uq_subscription_one_active_per_tenant.
    """
    tenant = TenantFactory()
    plan1 = PlanFactory(name="Plan A")
    plan2 = PlanFactory(name="Plan B")
    now = timezone.now()

    Subscription.objects.create(
        tenant=tenant,
        plan=plan1,
        status=Subscription.Status.ACTIVE,
        starts_at=now,
    )

    with pytest.raises(IntegrityError):
        Subscription.objects.create(
            tenant=tenant,
            plan=plan2,
            status=Subscription.Status.ACTIVE,
            starts_at=now,
        )


@pytest.mark.django_db
def test_subscription_multiple_non_active_allowed_for_same_tenant() -> None:
    """Historical non-active subscriptions (past_due, cancelled, expired)
    coexist peacefully.
    """
    tenant = TenantFactory()
    plan = PlanFactory()
    now = timezone.now()

    sub1 = Subscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.EXPIRED,
        starts_at=now - timedelta(days=60),
        ends_at=now - timedelta(days=30),
    )
    sub2 = Subscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.CANCELLED,
        starts_at=now - timedelta(days=30),
        ends_at=now - timedelta(days=10),
    )
    sub_active = Subscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now,
    )

    assert sub1.id is not None
    assert sub2.id is not None
    assert sub_active.id is not None
    assert Subscription.objects.filter(tenant=tenant).count() == 3


@pytest.mark.django_db
def test_subscription_different_tenants_can_have_active_subscriptions() -> None:
    """Distinct tenants can each hold an active subscription concurrently."""
    tenant1 = TenantFactory()
    tenant2 = TenantFactory()
    plan = PlanFactory()
    now = timezone.now()

    sub1 = Subscription.objects.create(
        tenant=tenant1,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now,
    )
    sub2 = Subscription.objects.create(
        tenant=tenant2,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now,
    )

    assert sub1.id != sub2.id
    assert sub1.status == Subscription.Status.ACTIVE
    assert sub2.status == Subscription.Status.ACTIVE


@pytest.mark.django_db
def test_plan_and_subscription_factories() -> None:
    """PlanFactory and SubscriptionFactory instantiate valid records."""
    plan = PlanFactory()
    assert plan.price == Decimal("5000.00")

    sub = SubscriptionFactory()
    assert sub.status == Subscription.Status.ACTIVE
    assert sub.tenant is not None
    assert sub.plan is not None
