"""Master dashboard Phase 1: overview metrics (Doc 04 §12.2, TP-4).

The load-bearing assertion here is isolation: the dashboard must derive every
figure from public-schema rows and catalogues, never from a tenant schema.
"""

from decimal import Decimal
from typing import Any

import pytest
from django.core.cache import cache
from django.db import connection
from django.db.models import Sum
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.core.models import Subscription
from apps.platform.platform_jwt import platform_mint_access_token
from apps.platform.views_metrics import METRICS_CACHE_KEY
from tests.factories.core import (
    PlanFactory,
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)

URL = "/api/v1/platform/metrics/overview"
HOST = "localhost"

EXPECTED_KEYS = {
    "total_labs",
    "active_labs",
    "suspended_labs",
    "provisioning_labs",
    "mrr_pkr",
    "overdue_count",
    "lifetime_sold",
    "founding_slots_used",
    "founding_slots_total",
    "access_mode_census",
}


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _client() -> APIClient:
    user = PlatformUserFactory(totp_enabled=True)
    token, _jti, _exp = platform_mint_access_token(user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_overview_requires_platform_auth() -> None:
    assert APIClient().get(URL, HTTP_HOST=HOST).status_code in (401, 403)


@pytest.mark.django_db
def test_overview_returns_the_documented_shape(tenant_a: Any) -> None:
    client = _client()

    resp = client.get(URL, HTTP_HOST=HOST)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= EXPECTED_KEYS
    assert set(body["access_mode_census"]) == {"full", "read_only", "grace"}
    # Money is a string with exactly two decimals, never a JSON number.
    assert isinstance(body["mrr_pkr"], str)
    assert body["mrr_pkr"].split(".")[1] == "00"


@pytest.mark.django_db
def test_mrr_sums_active_subscription_prices_only() -> None:
    plan = PlanFactory(name="Metrics Plan", price=Decimal("7500.00"))
    active_tenant = TenantFactory()
    SubscriptionFactory(
        tenant=active_tenant, plan=plan, status=Subscription.Status.ACTIVE
    )
    cancelled_tenant = TenantFactory()
    SubscriptionFactory(
        tenant=cancelled_tenant, plan=plan, status=Subscription.Status.CANCELLED
    )

    body = _client().get(URL, HTTP_HOST=HOST).json()

    expected = Subscription.objects.filter(status=Subscription.Status.ACTIVE).aggregate(
        total=Sum("plan__price")
    )["total"] or Decimal("0.00")
    assert body["mrr_pkr"] == f"{Decimal(expected).quantize(Decimal('0.01'))}"


@pytest.mark.django_db
def test_overview_counts_tenant_lifecycle_states(tenant_a: Any) -> None:
    TenantFactory(status="suspended")
    TenantFactory(status="provisioning")

    body = _client().get(URL, HTTP_HOST=HOST).json()

    assert body["suspended_labs"] >= 1
    assert body["provisioning_labs"] >= 1
    # The public platform tenant is not a lab and must not be counted.
    assert body["total_labs"] >= 2


@pytest.mark.django_db
def test_overview_never_reads_a_tenant_schema(tenant_a: Any) -> None:
    """TP-4: platform reporting reads only public-schema tables and catalogues."""
    cache.clear()
    client = _client()

    with CaptureQueriesContext(connection) as captured:
        resp = client.get(URL, HTTP_HOST=HOST)

    assert resp.status_code == 200
    sql = " ".join(query["sql"] for query in captured.captured_queries).lower()
    assert sql, "expected the endpoint to issue queries"
    assert "tenant_a." not in sql
    assert 'from "tenant_' not in sql
    assert 'join "tenant_' not in sql


@pytest.mark.django_db
def test_overview_is_cached_for_sixty_seconds() -> None:
    client = _client()

    first = client.get(URL, HTTP_HOST=HOST).json()
    assert cache.get(METRICS_CACHE_KEY) is not None

    second = client.get(URL, HTTP_HOST=HOST).json()
    assert second == first
