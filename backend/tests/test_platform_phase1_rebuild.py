"""Phase 1 Platform Dashboard Rebuild Tests.

Covers:
1. Plan.max_staff and active plans seeding
2. Tenant provisioning with extended fields & master temporary credentials
3. Labs List with city, branch_count, plan, and MRR contribution
4. Lab Detail with owner contact, quotas, signals, and audit timeline
5. Overview metrics with 6-month growth, overdue list, and needs attention
"""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core.models import Plan, PlatformAudit, Subscription, Tenant
from apps.platform.platform_jwt import platform_mint_access_token
from tests.factories.core import (
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)


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
def test_plan_model_has_max_staff_and_endpoint_returns_it() -> None:
    plan = Plan.objects.create(
        name="Test Starter Tier",
        price=Decimal("2999.00"),
        max_branches=1,
        max_staff=5,
        is_active=True,
    )
    client = _client()
    resp = client.get("/api/v1/platform/plans", HTTP_HOST="localhost")
    assert resp.status_code == 200
    plans = resp.json()["plans"]
    matching = [p for p in plans if p["id"] == str(plan.id)]
    assert len(matching) == 1
    assert matching[0]["max_staff"] == 5
    assert matching[0]["max_branches"] == 1
    assert matching[0]["price"] == "2999.00"


@pytest.mark.django_db
def test_provision_tenant_with_extended_fields_and_temp_credential() -> None:
    plan = Plan.objects.create(
        name="Test Growth Tier",
        price=Decimal("5999.00"),
        max_branches=3,
        max_staff=None,
        is_active=True,
    )
    client = _client()
    slug = f"testlab{uuid.uuid4().hex[:6]}"
    payload = {
        "name": "Al-Razi Diagnostic Centre",
        "slug": slug,
        "plan_id": str(plan.id),
        "owner_name": "Dr. Salman Tariq",
        "owner_email": "salman@alrazidiag.com",
        "city": "Lahore",
        "province": "Punjab",
        "phone": "+92 300 1234567",
        "whatsapp": "+92 300 1234567",
        "staff_seats": 10,
        "branch_count": 2,
        "enabled_roles": ["manager", "technician", "pathologist"],
    }
    resp = client.post(
        "/api/v1/platform/tenants",
        data=payload,
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["slug"] == slug
    assert "temp_password" in data
    assert data["temp_password"].startswith("LBF-")
    assert data["temp_password"].endswith("#")

    tenant = Tenant.objects.get(slug=slug)
    assert tenant.city == "Lahore"
    assert tenant.province == "Punjab"
    assert tenant.owner_name == "Dr. Salman Tariq"
    assert tenant.owner_email == "salman@alrazidiag.com"
    assert tenant.owner_phone == "+92 300 1234567"
    assert tenant.staff_seats_limit == 10
    assert tenant.temp_password == data["temp_password"]
    assert tenant.temp_password_expires_at is not None


@pytest.mark.django_db
def test_labs_list_returns_rich_attributes() -> None:
    plan = Plan.objects.create(
        name="Test Scale Tier",
        price=Decimal("9999.00"),
        max_branches=None,
        max_staff=None,
        is_active=True,
    )
    tenant = TenantFactory(
        name="Lahore Central Lab",
        city="Lahore",
        branch_count=3,
        status=Tenant.Status.ACTIVE,
    )
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)

    client = _client()
    resp = client.get("/api/v1/platform/tenants", HTTP_HOST="localhost")
    assert resp.status_code == 200
    labs = resp.json()["tenants"]
    matching = [item for item in labs if item["id"] == str(tenant.id)]
    assert len(matching) == 1
    lab = matching[0]
    assert lab["city"] == "Lahore"
    assert lab["branch_count"] == 3
    assert lab["plan_name"] == "Test Scale Tier"
    assert lab["plan_price"] == "9999.00"
    assert lab["mrr_contribution"] == "9999.00"


@pytest.mark.django_db
def test_lab_detail_returns_quotas_signals_and_audit() -> None:
    plan = Plan.objects.create(
        name="Test Scale Plus",
        price=Decimal("9999.00"),
        max_branches=10,
        max_staff=50,
        is_active=True,
    )
    tenant = TenantFactory(
        name="Islamabad Medical Lab",
        city="Islamabad",
        province="ICT",
        owner_name="Dr. Tariq",
        owner_email="tariq@islab.com",
        owner_phone="+92 321 9876543",
        branch_count=4,
        staff_seats_limit=50,
        staff_count=12,
        status=Tenant.Status.ACTIVE,
    )
    SubscriptionFactory(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
    PlatformAudit.objects.create(
        action="tenant.provisioned",
        entity_type="tenant",
        entity_id=tenant.id,
        after_jsonb={"note": "Provisioned successfully"},
    )

    client = _client()
    resp = client.get(f"/api/v1/platform/tenants/{tenant.id}", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Islamabad Medical Lab"
    assert data["city"] == "Islamabad"
    assert data["owner"]["name"] == "Dr. Tariq"
    assert data["owner"]["email"] == "tariq@islab.com"
    assert data["owner"]["phone"] == "+92 321 9876543"
    assert data["branches_used"] == 4
    assert data["branches_limit"] == 10
    assert data["staff_seats_limit"] == 50
    assert data["staff_count"] == 12
    assert "audit_timeline" in data
    assert len(data["audit_timeline"]) >= 1


@pytest.mark.django_db
def test_overview_metrics_extended_signals() -> None:
    client = _client()
    # Test both /api/v1/platform/metrics and /api/v1/platform/metrics/overview
    for endpoint in ("/api/v1/platform/metrics", "/api/v1/platform/metrics/overview"):
        resp = client.get(endpoint, HTTP_HOST="localhost")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_labs" in data
        assert "active_labs" in data
        assert "mrr_pkr" in data
        assert "lifetime_revenue_pkr" in data
        assert "overdue_subscriptions" in data
        assert "count" in data["overdue_subscriptions"]
        assert "labs_growth_6months" in data
        assert len(data["labs_growth_6months"]) == 6
        assert "needs_attention" in data
        assert "recent_audits" in data
