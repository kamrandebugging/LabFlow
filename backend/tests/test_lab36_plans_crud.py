"""LAB-36 (KAN-161): Plans CRUD + subscription changes (Doc 04 §11.1, §15.1)."""

from decimal import Decimal
from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core.models import PlatformAudit, Subscription
from apps.platform.access import access_mode_cache_key, tenant_access_mode
from tests.factories.core import (
    PlanFactory,
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)


def _platform_auth_headers(user: Any) -> dict[str, str]:
    """Build a valid platform access token (sub / role / jti / iat / exp / typ)."""
    from apps.platform.platform_jwt import platform_mint_access_token

    token, _jti, _exp = platform_mint_access_token(user.id, "super_admin")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def platform_admin() -> Any:
    user = PlatformUserFactory(totp_enabled=True, is_active=True)
    return user


@pytest.fixture
def authed_client(platform_admin: Any) -> APIClient:
    client = APIClient()
    headers = _platform_auth_headers(platform_admin)
    client.defaults.update(headers)
    return client


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# GET /platform/plans
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_plans_returns_all(authed_client: APIClient) -> None:
    PlanFactory(name="Starter", price=Decimal("3000.00"))
    PlanFactory(name="Pro", price=Decimal("9000.00"), is_active=False)

    resp = authed_client.get("/api/v1/platform/plans", HTTP_HOST="localhost")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()["plans"]}
    assert {"Starter", "Pro"} <= names


@pytest.mark.django_db
def test_list_plans_requires_platform_auth() -> None:
    client = APIClient()
    resp = client.get("/api/v1/platform/plans", HTTP_HOST="localhost")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /platform/plans
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_plan_success(authed_client: APIClient) -> None:
    resp = authed_client.post(
        "/api/v1/platform/plans",
        HTTP_HOST="localhost",
        data={
            "name": "Enterprise",
            "price": "15000.00",
            "max_branches": 10,
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Enterprise"
    assert body["price"] == "15000.00"
    assert body["max_branches"] == 10
    assert body["is_active"] is True

    # Audit row written
    assert PlatformAudit.objects.filter(action="plan.created").exists()


@pytest.mark.django_db
def test_create_plan_rejects_negative_price(authed_client: APIClient) -> None:
    resp = authed_client.post(
        "/api/v1/platform/plans",
        HTTP_HOST="localhost",
        data={"name": "Bad", "price": "-100.00"},
        format="json",
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_create_plan_rejects_duplicate_name(authed_client: APIClient) -> None:
    PlanFactory(name="Starter")
    resp = authed_client.post(
        "/api/v1/platform/plans",
        HTTP_HOST="localhost",
        data={"name": "Starter", "price": "5000.00"},
        format="json",
    )
    assert resp.status_code == 422


@pytest.mark.django_db
def test_create_plan_money_must_be_string(authed_client: APIClient) -> None:
    resp = authed_client.post(
        "/api/v1/platform/plans",
        HTTP_HOST="localhost",
        data={"name": "Numeric", "price": 5000.00},
        format="json",
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "money_must_be_string"


# ---------------------------------------------------------------------------
# POST /platform/plans/{id}/retire
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_retire_plan_sets_inactive(authed_client: APIClient) -> None:
    plan = PlanFactory(name="Legacy")
    resp = authed_client.post(
        f"/api/v1/platform/plans/{plan.id}/retire",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    plan.refresh_from_db()
    assert plan.is_active is False
    assert PlatformAudit.objects.filter(action="plan.retired").exists()


@pytest.mark.django_db
def test_retire_referenced_plan_returns_409(authed_client: APIClient) -> None:
    plan = PlanFactory(name="InUse")
    tenant = TenantFactory()
    SubscriptionFactory(tenant=tenant, plan=plan)
    resp = authed_client.post(
        f"/api/v1/platform/plans/{plan.id}/retire",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "plan_in_use"
    plan.refresh_from_db()
    assert plan.is_active is True


@pytest.mark.django_db
def test_retire_nonexistent_plan_returns_404(authed_client: APIClient) -> None:
    import uuid

    resp = authed_client.post(
        f"/api/v1/platform/plans/{uuid.uuid4()}/retire",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /platform/tenants/{id}/subscription
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_change_subscription_creates_new_closes_old(
    authed_client: APIClient,
) -> None:
    tenant = TenantFactory()
    old_plan = PlanFactory(name="Old")
    new_plan = PlanFactory(name="New")
    old_sub = SubscriptionFactory(
        tenant=tenant, plan=old_plan, status=Subscription.Status.ACTIVE
    )

    resp = authed_client.post(
        f"/api/v1/platform/tenants/{tenant.id}/subscription",
        HTTP_HOST="localhost",
        data={
            "plan_id": str(new_plan.id),
            "status": "active",
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["plan_id"] == str(new_plan.id)

    # Old subscription closed
    old_sub.refresh_from_db()
    assert old_sub.status != Subscription.Status.ACTIVE

    # New subscription is active
    new_sub = Subscription.objects.get(id=body["id"])
    assert new_sub.status == Subscription.Status.ACTIVE
    assert new_sub.tenant_id == tenant.id

    # Audit with before/after
    audit = PlatformAudit.objects.filter(action="subscription.changed").first()
    assert audit is not None


@pytest.mark.django_db
def test_change_subscription_invalidates_access_mode_cache(
    authed_client: APIClient,
) -> None:
    tenant: Any = TenantFactory()
    old_plan = PlanFactory(name="Old2")
    new_plan = PlanFactory(name="New2")
    SubscriptionFactory(
        tenant=tenant,
        plan=old_plan,
        status=Subscription.Status.CANCELLED,
    )
    # Prime cache as read_only
    assert tenant_access_mode(tenant) == "read_only"
    assert cache.get(access_mode_cache_key(tenant.slug)) == "read_only"

    resp = authed_client.post(
        f"/api/v1/platform/tenants/{tenant.id}/subscription",
        HTTP_HOST="localhost",
        data={"plan_id": str(new_plan.id), "status": "active"},
        format="json",
    )
    assert resp.status_code == 201
    # Cache invalidated — fresh computation returns full
    assert tenant_access_mode(tenant) == "full"


@pytest.mark.django_db
def test_change_subscription_rejects_inactive_plan(
    authed_client: APIClient,
) -> None:
    tenant = TenantFactory()
    plan = PlanFactory(name="Retired", is_active=False)
    SubscriptionFactory(tenant=tenant, plan=PlanFactory())

    resp = authed_client.post(
        f"/api/v1/platform/tenants/{tenant.id}/subscription",
        HTTP_HOST="localhost",
        data={"plan_id": str(plan.id), "status": "active"},
        format="json",
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "plan_inactive"
