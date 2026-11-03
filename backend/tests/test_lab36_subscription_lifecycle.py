"""LAB-36 (KAN-161): Subscription lifecycle — access mode, read-only middleware,
plans CRUD, subscription changes (Doc 04 §11.1, §11.2, §15.1)."""

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from apps.core.models import Subscription
from apps.platform.access import (
    ACCESS_MODE_CACHE_TTL,
    access_mode_cache_key,
    invalidate_access_mode_cache,
    tenant_access_mode,
)
from tests.factories.core import (
    PlanFactory,
    SubscriptionFactory,
    TenantFactory,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# tenant_access_mode
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_access_mode_active_subscription_returns_full() -> None:
    tenant: Any = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
    assert tenant_access_mode(tenant) == "full"


@pytest.mark.django_db
def test_access_mode_past_due_within_grace_returns_full() -> None:
    tenant: Any = TenantFactory()
    plan = PlanFactory()
    now = timezone.now()
    # past_due set 5 days ago — within 14-day grace
    sub = SubscriptionFactory(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.PAST_DUE,
    )
    sub.updated_at = now - timedelta(days=5)
    Subscription.objects.filter(id=sub.id).update(updated_at=now - timedelta(days=5))
    assert tenant_access_mode(tenant) == "full"


@pytest.mark.django_db
def test_access_mode_past_due_after_grace_returns_read_only() -> None:
    tenant: Any = TenantFactory()
    plan = PlanFactory()
    now = timezone.now()
    sub = SubscriptionFactory(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.PAST_DUE,
    )
    Subscription.objects.filter(id=sub.id).update(updated_at=now - timedelta(days=15))
    assert tenant_access_mode(tenant) == "read_only"


@pytest.mark.django_db
def test_access_mode_cancelled_returns_read_only() -> None:
    tenant: Any = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.CANCELLED)
    assert tenant_access_mode(tenant) == "read_only"


@pytest.mark.django_db
def test_access_mode_expired_returns_read_only() -> None:
    tenant: Any = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.EXPIRED)
    assert tenant_access_mode(tenant) == "read_only"


@pytest.mark.django_db
def test_access_mode_no_subscription_returns_read_only() -> None:
    tenant: Any = TenantFactory()
    assert tenant_access_mode(tenant) == "read_only"


@pytest.mark.django_db
def test_access_mode_uses_redis_cache() -> None:
    tenant: Any = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)

    # First call populates cache
    assert tenant_access_mode(tenant) == "full"
    cached = cache.get(access_mode_cache_key(tenant.slug))
    assert cached == "full"

    # Change DB directly — cached value still returned
    Subscription.objects.filter(tenant=tenant).update(
        status=Subscription.Status.CANCELLED
    )
    assert tenant_access_mode(tenant) == "full"

    # After invalidation, fresh value computed
    invalidate_access_mode_cache(tenant.slug)
    assert tenant_access_mode(tenant) == "read_only"


def test_access_mode_cache_key_format() -> None:
    assert access_mode_cache_key("citylab") == "tenant:citylab:access-mode"


def test_access_mode_cache_ttl_is_60_seconds() -> None:
    assert ACCESS_MODE_CACHE_TTL == 60


# ---------------------------------------------------------------------------
# Read-only middleware
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_middleware_blocks_write_in_read_only() -> None:
    from apps.platform.middleware import SubscriptionReadOnlyMiddleware

    tenant = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.CANCELLED)

    factory = RequestFactory()
    request = factory.post("/api/v1/patients", data={})
    request.tenant = tenant

    middleware = SubscriptionReadOnlyMiddleware(get_response=MagicMock())
    response = middleware(request)

    assert response.status_code == 403
    assert response["Content-Type"] == "application/problem+json"


@pytest.mark.django_db
def test_middleware_allows_read_in_read_only() -> None:
    from apps.platform.middleware import SubscriptionReadOnlyMiddleware

    tenant = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.CANCELLED)

    factory = RequestFactory()
    request = factory.get("/api/v1/patients")
    request.tenant = tenant

    mock_response = MagicMock()
    mock_response.status_code = 200
    middleware = SubscriptionReadOnlyMiddleware(
        get_response=MagicMock(return_value=mock_response)
    )
    response = middleware(request)
    assert response.status_code == 200


@pytest.mark.django_db
def test_middleware_allows_write_in_full_mode() -> None:
    from apps.platform.middleware import SubscriptionReadOnlyMiddleware

    tenant = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)

    factory = RequestFactory()
    request = factory.post("/api/v1/patients", data={})
    request.tenant = tenant

    mock_response = MagicMock()
    mock_response.status_code = 201
    middleware = SubscriptionReadOnlyMiddleware(
        get_response=MagicMock(return_value=mock_response)
    )
    response = middleware(request)
    assert response.status_code == 201


@pytest.mark.django_db
def test_middleware_exempts_report_access() -> None:
    """Patient report-access (TP-8) is exempt from read-only gate."""
    from apps.platform.middleware import SubscriptionReadOnlyMiddleware

    tenant = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.CANCELLED)

    factory = RequestFactory()
    request = factory.get("/api/v1/reports/access/abc123")
    request.tenant = tenant

    mock_response = MagicMock()
    mock_response.status_code = 200
    middleware = SubscriptionReadOnlyMiddleware(
        get_response=MagicMock(return_value=mock_response)
    )
    response = middleware(request)
    assert response.status_code == 200


@pytest.mark.django_db
def test_middleware_exempts_owner_export() -> None:
    """Owner data export is exempt — tenant must leave with its data."""
    from apps.platform.middleware import SubscriptionReadOnlyMiddleware

    tenant = TenantFactory()
    plan = PlanFactory()
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.CANCELLED)

    factory = RequestFactory()
    request = factory.post("/api/v1/exports", data={})
    request.tenant = tenant

    mock_response = MagicMock()
    mock_response.status_code = 202
    middleware = SubscriptionReadOnlyMiddleware(
        get_response=MagicMock(return_value=mock_response)
    )
    response = middleware(request)
    assert response.status_code == 202
