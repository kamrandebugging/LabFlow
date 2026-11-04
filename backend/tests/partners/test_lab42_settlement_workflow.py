"""LAB-42 (KAN-261): Settlement workflow — approve, cancel, mark-paid, send.

Doc 05 §7.3–§7.6, §10; Doc 03 §6.1 conventions.
Verify: RS-29, RS-31, RS-32, RS-41.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, Role
from apps.core.models import Plan, Subscription, Tenant
from apps.notifications.models import Notification
from apps.partners.models import (
    Settlement,
    SettlementLine,
    ShareLedgerEntry,
)
from tests.factories import (
    PlanFactory,
    ReferralPartnerFactory,
    SettlementFactory,
    SettlementLineFactory,
    StaffUserFactory,
)


def _jwt(staff_id: uuid.UUID | Any, tenant_slug: str, role: str = "owner") -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    now = int(timezone.now().timestamp())
    return str(
        jwt.encode(
            {
                "sub": str(staff_id),
                "tenant": tenant_slug,
                "role": role,
                "typ": "access",
                "jti": uuid.uuid4().hex,
                "iat": now,
                "exp": now + 3600,
            },
            str(signing_key),
            algorithm="HS256",
        )
    )


def _auth(client: APIClient, staff: Any, tenant: Tenant, role: str = "owner") -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_jwt(staff.id, tenant.slug, role)}")


@pytest.fixture
def api_client() -> APIClient:
    client = APIClient()
    # django-tenants resolves the tenant from the Host header.
    client.defaults["HTTP_HOST"] = "tenant-a.localhost"
    return client


@pytest.fixture
def active_subscription(tenant_a: Tenant) -> Any:
    """Active subscription so the tenant is in full access mode (Doc 04 §11.2)."""
    plan = PlanFactory(name="Lab42Plan", price=Decimal("100.00"))
    with schema_context("public"):
        sub = Subscription.objects.create(
            tenant=tenant_a,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(days=30),
        )
    yield sub
    with schema_context("public"):
        Subscription.objects.filter(id=sub.id).delete()
        Plan.objects.filter(id=plan.id).delete()


def _make_owner(tenant: Tenant) -> Any:
    with schema_context(tenant.schema_name):
        return StaffUserFactory(tenant_wide=True, role=Role.OWNER)


def _make_manager(tenant: Tenant) -> Any:
    with schema_context(tenant.schema_name):
        return StaffUserFactory(tenant_wide=True, role=Role.MANAGER)


def _draft_settlement(tenant: Tenant, **kwargs: Any) -> Any:
    with schema_context(tenant.schema_name):
        partner = kwargs.pop("referral_partner", None) or ReferralPartnerFactory(
            email="doc@example.com"
        )
        return SettlementFactory(referral_partner=partner, **kwargs)


def _etag(settlement: Settlement) -> str:
    return settlement.updated_at.isoformat()


@pytest.mark.django_db(transaction=True)
class TestSettlementApprove:
    def test_approve_draft_happy_path(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)

        with patch("apps.partners.tasks.finalize_settlement.delay") as mock_delay:
            resp = api_client.post(
                f"/api/v1/settlements/{settlement.id}/approve",
                HTTP_IF_MATCH=_etag(settlement),
            )

        assert resp.status_code == 200, resp.content[:500]
        body = resp.json()
        assert body["status"] == "APPROVED"
        assert body["approved_by"] == str(owner.id)
        assert body["approved_at"] is not None
        mock_delay.assert_called_once()

        with schema_context(tenant_a.schema_name):
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.APPROVED
            assert settlement.approved_by_id == owner.id
            assert AuditLog.objects.filter(
                action="settlement.approved",
                entity_type="settlement",
                entity_id=settlement.id,
            ).exists()

    def test_approve_non_draft_409(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a, status=Settlement.Status.APPROVED)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/approve",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_approve_stale_if_match_409_version_conflict(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/approve",
            HTTP_IF_MATCH="1999-01-01T00:00:00+00:00",
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "version_conflict"
        # §12.2: response carries the settlement's current state
        assert body["error"]["details"]["status"] == "DRAFT"

    def test_approve_missing_if_match_400(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(f"/api/v1/settlements/{settlement.id}/approve")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "if_match_required"

    def test_approve_non_owner_403(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        manager = _make_manager(tenant_a)
        settlement = _draft_settlement(tenant_a)
        _auth(api_client, manager, tenant_a, role="manager")

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/approve",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"

    def test_approve_read_only_subscription_403(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        # past-due subscription older than the 14-day grace → read-only
        plan = PlanFactory(name="RS37Plan", price=Decimal("100.00"))
        with schema_context("public"):
            sub = Subscription.objects.create(
                tenant=tenant_a,
                plan=plan,
                status=Subscription.Status.PAST_DUE,
                starts_at=timezone.now() - timedelta(days=60),
            )
            # auto_now blocks setting updated_at on create — backdate it.
            Subscription.objects.filter(id=sub.id).update(
                updated_at=timezone.now() - timedelta(days=20)
            )
        try:
            _auth(api_client, owner, tenant_a)

            resp = api_client.post(
                f"/api/v1/settlements/{settlement.id}/approve",
                HTTP_IF_MATCH=_etag(settlement),
            )
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "subscription_read_only"
        finally:
            with schema_context("public"):
                Subscription.objects.filter(id=sub.id).delete()
                Plan.objects.filter(id=plan.id).delete()

    def test_approve_unauthenticated_401(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        settlement = _draft_settlement(tenant_a)
        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/approve",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 401

    def test_approve_not_found_404(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        _auth(api_client, owner, tenant_a)
        resp = api_client.post(
            f"/api/v1/settlements/{uuid.uuid4()}/approve",
            HTTP_IF_MATCH="x",
        )
        assert resp.status_code == 404

    def test_rs29_concurrent_approvals_one_wins(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        """RS-29: two Owners approve the same DRAFT — one 200, one 409."""
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        etag = _etag(settlement)
        _auth(api_client, owner, tenant_a)

        with patch("apps.partners.tasks.finalize_settlement.delay"):
            first = api_client.post(
                f"/api/v1/settlements/{settlement.id}/approve",
                HTTP_IF_MATCH=etag,
            )
        assert first.status_code == 200

        # Second approval with the now-stale token
        with patch("apps.partners.tasks.finalize_settlement.delay"):
            second = api_client.post(
                f"/api/v1/settlements/{settlement.id}/approve",
                HTTP_IF_MATCH=etag,
            )
        # Either version_conflict (stale token) or invalid_state_transition
        # (already approved) — both are 409, never a double approval.
        assert second.status_code == 409
        assert second.json()["error"]["code"] in (
            "version_conflict",
            "invalid_state_transition",
        )


@pytest.mark.django_db(transaction=True)
class TestSettlementCancel:
    def test_cancel_draft_happy_path(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        with schema_context(tenant_a.schema_name):
            line = SettlementLineFactory(settlement=settlement)
            entry_id = line.share_ledger_entry_id
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/cancel",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 200, resp.content[:500]
        assert resp.json()["status"] == "CANCELLED"

        with schema_context(tenant_a.schema_name):
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.CANCELLED
            # ST-17: lines stay on the cancelled settlement
            assert SettlementLine.objects.filter(settlement=settlement).count() == 1
            # ST-17: ledger rows never change
            assert ShareLedgerEntry.objects.filter(id=entry_id).exists()
            assert AuditLog.objects.filter(
                action="settlement.cancelled",
                entity_type="settlement",
                entity_id=settlement.id,
            ).exists()

    def test_rs32_cancel_approved_422(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a, status=Settlement.Status.APPROVED)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/cancel",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "settlement_not_cancellable"

    def test_cancel_sent_422(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a, status=Settlement.Status.SENT)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/cancel",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "settlement_not_cancellable"

    def test_cancel_paid_422(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a, status=Settlement.Status.PAID)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/cancel",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "settlement_not_cancellable"

    def test_rs31_cancel_then_redraft(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        """RS-31: cancel DRAFT → old row CANCELLED with lines; re-draft works."""
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a, period="2026-09")
        with schema_context(tenant_a.schema_name):
            SettlementLineFactory(settlement=settlement)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/cancel",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 200

        with schema_context(tenant_a.schema_name):
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.CANCELLED
            # Re-draft: new row allowed because old is CANCELLED (partial unique)
            redraft = SettlementFactory(
                referral_partner=settlement.referral_partner,
                period="2026-09",
                status=Settlement.Status.DRAFT,
            )
            assert redraft.id != settlement.id
            assert redraft.status == Settlement.Status.DRAFT


@pytest.mark.django_db(transaction=True)
class TestSettlementMarkPaid:
    def _sent_settlement(self, tenant: Tenant) -> Settlement:
        return _draft_settlement(tenant, status=Settlement.Status.SENT)

    def test_mark_paid_happy_path(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = self._sent_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/mark-paid",
            {"reference": "IBFT-2026-11823"},
            format="json",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 200, resp.content[:500]
        assert resp.json()["status"] == "PAID"

        with schema_context(tenant_a.schema_name):
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.PAID
            # ST-14: reference lives in the audit row only — no column
            assert not hasattr(settlement, "paid_reference")
            audit = AuditLog.objects.get(
                action="settlement.mark_paid",
                entity_type="settlement",
                entity_id=settlement.id,
            )
            assert audit.after_jsonb["reference"] == "IBFT-2026-11823"  # type: ignore[index]
            assert audit.actor_id == owner.id

    def test_mark_paid_draft_409(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/mark-paid",
            {"reference": "x"},
            format="json",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_mark_paid_missing_reference_422(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = self._sent_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(
            f"/api/v1/settlements/{settlement.id}/mark-paid",
            {},
            format="json",
            HTTP_IF_MATCH=_etag(settlement),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.django_db(transaction=True)
class TestSettlementSend:
    def test_send_approved_happy_path(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a, status=Settlement.Status.APPROVED)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(f"/api/v1/settlements/{settlement.id}/send")
        assert resp.status_code == 200, resp.content[:500]

        with schema_context(tenant_a.schema_name):
            notif = Notification.objects.get(
                template_key="settlement_ready",
                recipient_type="partner",
                recipient_id=settlement.referral_partner_id,
            )
            assert notif.channel == "email"
            assert notif.status == Notification.Status.PENDING
            assert notif.idempotency_key
            assert AuditLog.objects.filter(
                action="settlement.send",
                entity_type="settlement",
                entity_id=settlement.id,
            ).exists()

    def test_send_sent_creates_fresh_copy_row(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        """DL-6: re-sending a SENT settlement creates a fresh notification row."""
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a, status=Settlement.Status.SENT)
        _auth(api_client, owner, tenant_a)

        first = api_client.post(f"/api/v1/settlements/{settlement.id}/send")
        second = api_client.post(f"/api/v1/settlements/{settlement.id}/send")
        assert first.status_code == 200
        assert second.status_code == 200

        with schema_context(tenant_a.schema_name):
            count = Notification.objects.filter(
                template_key="settlement_ready",
                recipient_id=settlement.referral_partner_id,
            ).count()
            assert count == 2

    def test_send_draft_409(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(f"/api/v1/settlements/{settlement.id}/send")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_send_missing_email_422(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        with schema_context(tenant_a.schema_name):
            partner = ReferralPartnerFactory(email=None)
        settlement = _draft_settlement(
            tenant_a,
            referral_partner=partner,
            status=Settlement.Status.APPROVED,
        )
        _auth(api_client, owner, tenant_a)

        resp = api_client.post(f"/api/v1/settlements/{settlement.id}/send")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "partner_email_missing"


@pytest.mark.django_db(transaction=True)
class TestSettlementListDetail:
    def test_list_owner_and_manager_ok(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        _draft_settlement(tenant_a)
        _auth(api_client, owner, tenant_a)
        resp = api_client.get("/api/v1/settlements")
        assert resp.status_code == 200
        assert "results" in resp.json()

    def test_list_receptionist_403(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        with schema_context(tenant_a.schema_name):
            recep = StaffUserFactory(tenant_wide=True, role=Role.RECEPTION)
        _auth(api_client, recep, tenant_a, role="receptionist")
        resp = api_client.get("/api/v1/settlements")
        assert resp.status_code == 403

    def test_list_filters(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        s1 = _draft_settlement(tenant_a, period="2026-09")
        _draft_settlement(tenant_a, period="2026-10")
        _auth(api_client, owner, tenant_a)

        resp = api_client.get("/api/v1/settlements?period=2026-09")
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()["results"]]
        assert [str(s1.id)] == ids

        resp = api_client.get("/api/v1/settlements?status=BOGUS")
        assert resp.status_code == 422

    def test_detail_includes_lines(
        self, tenant_a: Tenant, api_client: APIClient, active_subscription: Subscription
    ) -> None:
        owner = _make_owner(tenant_a)
        settlement = _draft_settlement(tenant_a)
        with schema_context(tenant_a.schema_name):
            SettlementLineFactory(settlement=settlement)
        _auth(api_client, owner, tenant_a)

        resp = api_client.get(f"/api/v1/settlements/{settlement.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 1
        assert body["lines"][0]["amount"] == "200.00"
        assert body["total"] == "200.00"
