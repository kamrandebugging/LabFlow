"""Phase 2 Platform Console Endpoints Tests (TDD).

Covers:
1. Subscriptions: list, detail, mark-paid, change-plan
2. Access Control: GET/PUT permissions, Owner role immutability, quota bounds
3. Users: lab owners from public Tenant metadata ONLY, platform operators
4. Demo Requests: public capture, platform inbox list, detail, patch, convert
5. Health: system status signals, schema sizes, failure retry
6. Settings: commercial tiers flowing to Plan records, founding offer, audit
7. Audit Log: filter by action, tenant, date range
"""

import contextlib
import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import (
    DemoRequest,
    Plan,
    PlatformAudit,
    PlatformUser,
    Subscription,
    SubscriptionPayment,
    Tenant,
    TenantFeatureFlag,
)
from apps.platform.platform_jwt import platform_mint_access_token
from tests.factories.core import (
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    with contextlib.suppress(Exception):
        cache.clear()
    yield
    with contextlib.suppress(Exception):
        cache.clear()


def _platform_user(**kwargs: Any) -> PlatformUser:
    return cast(PlatformUser, PlatformUserFactory(**kwargs))


def _auth_client(user: PlatformUser | None = None) -> APIClient:
    u = user or _platform_user(totp_enabled=True)
    token, _jti, _exp = platform_mint_access_token(u.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ==============================================================================
# 1. SUBSCRIPTIONS & MARK PAID
# ==============================================================================


@pytest.mark.django_db
def test_subscriptions_list_returns_summary_and_rows() -> None:
    plan, _ = Plan.objects.get_or_create(
        name="Growth", defaults={"price": Decimal("5999.00")}
    )
    t1 = TenantFactory(status=Tenant.Status.ACTIVE)
    sub = SubscriptionFactory(tenant=t1, plan=plan, status=Subscription.Status.ACTIVE)
    sub.billing_cycle = "monthly"
    sub.next_due = timezone.now().date() + timezone.timedelta(days=15)
    sub.save()

    client = _auth_client()
    resp = client.get("/api/v1/platform/subscriptions", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert "subscriptions" in data
    assert "summary" in data
    assert Decimal(data["summary"]["mrr"]) >= Decimal("5999.00")
    assert data["summary"]["founding_slots_total"] == 10

    matching = [s for s in data["subscriptions"] if s["id"] == str(sub.id)]
    assert len(matching) == 1
    row = matching[0]
    assert row["plan"]["name"] == "Growth"
    assert row["billing_cycle"] == "monthly"
    assert row["status"] == "active"


@pytest.mark.django_db
def test_mark_paid_requires_totp_creates_payment_and_audits() -> None:
    plan, _ = Plan.objects.get_or_create(
        name="Starter", defaults={"price": Decimal("2999.00")}
    )
    t = TenantFactory(status=Tenant.Status.ACTIVE)
    sub = SubscriptionFactory(tenant=t, plan=plan, status=Subscription.Status.PAST_DUE)

    # 1. User without TOTP gets 403 totp_required
    no_totp_user = _platform_user(totp_enabled=False)
    client_no_totp = _auth_client(no_totp_user)
    resp = client_no_totp.post(
        f"/api/v1/platform/subscriptions/{sub.id}/mark-paid",
        data={
            "method": "Bank Transfer",
            "reference": "TXN-123456",
            "amount": "2999.00",
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "totp_required"

    # 2. User with TOTP marks paid successfully
    user = _platform_user(totp_enabled=True)
    client = _auth_client(user)
    resp = client.post(
        f"/api/v1/platform/subscriptions/{sub.id}/mark-paid",
        data={
            "method": "Bank Transfer",
            "reference": "TXN-123456",
            "amount": "2999.00",
            "notes": "Verified against Meezan statement",
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Subscription is active and payment is saved
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE
    payment = SubscriptionPayment.objects.filter(subscription=sub).first()
    assert payment is not None
    assert payment.amount == Decimal("2999.00")
    assert payment.reference == "TXN-123456"
    assert payment.method == "Bank Transfer"

    # Audit recorded
    audit = PlatformAudit.objects.filter(
        action="payment.recorded", entity_id=sub.id
    ).first()
    assert audit is not None


@pytest.mark.django_db
def test_change_plan_updates_subscription_and_audits() -> None:
    p1, _ = Plan.objects.get_or_create(
        name="Starter", defaults={"price": Decimal("2999.00")}
    )
    p2, _ = Plan.objects.get_or_create(
        name="Scale", defaults={"price": Decimal("9999.00")}
    )
    t = TenantFactory(status=Tenant.Status.ACTIVE)
    sub = SubscriptionFactory(tenant=t, plan=p1, status=Subscription.Status.ACTIVE)

    client = _auth_client()
    resp = client.post(
        f"/api/v1/platform/subscriptions/{sub.id}/change-plan",
        data={"plan_id": str(p2.id), "billing_cycle": "annual"},
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    sub.refresh_from_db()
    assert sub.plan_id == p2.id
    assert sub.billing_cycle == "annual"

    audit = PlatformAudit.objects.filter(
        action="plan.changed", entity_id=sub.id
    ).first()
    assert audit is not None


# ==============================================================================
# 2. ACCESS CONTROL
# ==============================================================================


@pytest.mark.django_db
def test_access_control_get_and_put_with_owner_immutability() -> None:
    plan, _ = Plan.objects.get_or_create(
        name="Scale",
        defaults={
            "price": Decimal("9999.00"),
            "max_branches": 5,
            "max_staff": 25,
        },
    )
    t = TenantFactory(status=Tenant.Status.ACTIVE, enabled_roles=["owner", "manager"])
    SubscriptionFactory(tenant=t, plan=plan, status=Subscription.Status.ACTIVE)

    client = _auth_client()
    resp = client.get(f"/api/v1/platform/access/{t.id}", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == str(t.id)
    assert "owner" in data["enabled_roles"]

    # 1. Attempt to disable owner role -> 422 Unprocessable Entity
    resp = client.put(
        f"/api/v1/platform/access/{t.id}",
        data={
            "enabled_roles": ["manager", "receptionist"],
            "staff_limit": 10,
            "branch_limit": 2,
            "feature_flags": {"referral_partners": True},
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "owner_role_immutable"

    # 2. Valid save with owner included
    resp = client.put(
        f"/api/v1/platform/access/{t.id}",
        data={
            "enabled_roles": ["owner", "manager", "technician"],
            "staff_limit": 20,
            "branch_limit": 3,
            "feature_flags": {"referral_partners": True, "settlements": True},
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    t.refresh_from_db()
    assert "technician" in t.enabled_roles
    assert t.staff_seats_limit == 20

    flag = TenantFeatureFlag.objects.filter(
        tenant=t, flag_key="referral_partners"
    ).first()
    assert flag is not None
    assert flag.enabled is True

    audit = PlatformAudit.objects.filter(action="role.updated", entity_id=t.id).first()
    assert audit is not None


# ==============================================================================
# 3. USERS (OWNER METADATA ONLY — NEVER TENANT STAFF)
# ==============================================================================


@pytest.mark.django_db
def test_users_list_and_invite() -> None:
    t = TenantFactory(
        name="Alpha Diagnostic",
        owner_name="Dr. Tariq",
        owner_email="tariq@alpha.pk",
        owner_phone="+923001234567",
    )
    client = _auth_client()

    resp = client.get("/api/v1/platform/users", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert "lab_owners" in data
    assert "platform_team" in data
    assert "invitations" in data

    owner_item = next((o for o in data["lab_owners"] if o["id"] == str(t.id)), None)
    assert owner_item is not None
    assert owner_item["owner_name"] == "Dr. Tariq"
    assert owner_item["owner_email"] == "tariq@alpha.pk"

    # Invite new platform user
    resp = client.post(
        "/api/v1/platform/users/invite",
        data={"email": "operator.support@labflow.app", "role": "support"},
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ==============================================================================
# 4. DEMO REQUESTS
# ==============================================================================


@pytest.mark.django_db
def test_demo_request_lifecycle() -> None:
    # 1. Public capture endpoint (no auth needed)
    anon_client = APIClient()
    resp = anon_client.post(
        "/api/v1/demo-requests",
        data={
            "lab_name": "Gujranwala Labs",
            "contact_person": "Dr. Bilal",
            "whatsapp": "+923214567890",
            "message": "Interested in 3 branches setup",
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 201
    req_id = resp.json()["id"]

    # 2. Platform list
    client = _auth_client()
    resp = client.get("/api/v1/platform/demo-requests", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["new_count"] >= 1
    req_item = next((r for r in data["requests"] if r["id"] == req_id), None)
    assert req_item is not None
    assert req_item["contact_person"] == "Dr. Bilal"

    # 3. Patch status & notes
    resp = client.patch(
        f"/api/v1/platform/demo-requests/{req_id}",
        data={"status": "demo_done", "notes": "Completed zoom walkthrough"},
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    req = DemoRequest.objects.get(id=req_id)
    assert req.status == DemoRequest.Status.DEMO_DONE
    assert req.notes == "Completed zoom walkthrough"

    # 4. Convert to lab
    tenant = TenantFactory(name="Gujranwala Labs")
    resp = client.post(
        f"/api/v1/platform/demo-requests/{req_id}/convert",
        data={"tenant_id": str(tenant.id)},
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    req.refresh_from_db()
    assert req.status == DemoRequest.Status.CONVERTED
    assert req.converted_tenant_id == tenant.id


# ==============================================================================
# 5. SYSTEM HEALTH
# ==============================================================================


@pytest.mark.django_db
def test_system_health_signals_and_retry() -> None:
    client = _auth_client()
    resp = client.get("/api/v1/platform/health", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert "report_generation" in data
    assert "deliveries" in data
    assert "webhooks" in data
    assert "celery_queue" in data
    assert "schema_sizes" in data
    assert "failures" in data

    # Retry endpoint
    resp = client.post(
        "/api/v1/platform/health/failures/job-999/retry",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued_retry"


# ==============================================================================
# 6. SETTINGS & PLAN PRICE FLOW
# ==============================================================================


@pytest.mark.django_db
def test_platform_settings_read_and_update_flows_to_plans() -> None:
    p_starter, _ = Plan.objects.get_or_create(
        name="Starter", defaults={"price": Decimal("2999.00")}
    )
    client = _auth_client()

    resp = client.get("/api/v1/platform/settings", HTTP_HOST="localhost")
    assert resp.status_code == 200
    data = resp.json()
    assert "commercial_tiers" in data
    assert "founding_offer" in data
    assert "platform_toggles" in data

    # Update commercial tiers (Starter updated to 3499.00)
    resp = client.put(
        "/api/v1/platform/settings",
        data={
            "section": "commercial_tiers",
            "data": {
                "starter_price": "3499.00",
                "growth_price": "5999.00",
                "scale_price": "9999.00",
                "lifetime_single_price": "71999.00",
                "lifetime_multi_price": "143999.00",
                "annual_maintenance_pct": 18,
            },
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    p_starter.refresh_from_db()
    assert p_starter.price == Decimal("3499.00")

    # Verify audit entry
    audit = PlatformAudit.objects.filter(action="settings.updated").first()
    assert audit is not None


# ==============================================================================
# 7. AUDIT LOG FILTERING
# ==============================================================================


@pytest.mark.django_db
def test_audit_log_filtering_by_action_and_tenant() -> None:
    tid = uuid.uuid4()
    PlatformAudit.objects.create(
        action="payment.recorded",
        entity_type="tenant",
        entity_id=tid,
        before_jsonb={"status": "past_due"},
        after_jsonb={"status": "active"},
    )
    PlatformAudit.objects.create(
        action="role.updated",
        entity_type="tenant",
        entity_id=tid,
        before_jsonb={},
        after_jsonb={"roles": ["owner"]},
    )

    client = _auth_client()
    resp = client.get(
        f"/api/v1/platform/audit?action=payment.recorded&tenant_id={tid}",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 200
    audits = resp.json()["audits"]
    assert len(audits) >= 1
    assert all(a["action"] == "payment.recorded" for a in audits)
