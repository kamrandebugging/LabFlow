"""Tests for ShareLedgerListView (GET /api/v1/referral-partners/ledger).

Doc 02 §5.8, Doc 05 §6, Screens 38–42.
- Read-only: Owner and Manager can list ledger entries
- Other roles return 403 Forbidden
- Filters: partner_id, period (YYYY-MM), rule_id, limit, cursor
- Response includes results, next_cursor, and totals {count, amount}
- Settlement join: null when un-settled, populated when in active settlement
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.core.models import Tenant
from apps.partners.models import Settlement
from tests.factories import (
    PaymentFactory,
    ReferralPartnerFactory,
    RevenueShareRuleFactory,
    SettlementFactory,
    SettlementLineFactory,
    ShareLedgerEntryFactory,
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
                "iss": "labflow",
                "aud": "labflow-api",
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
    client.defaults["HTTP_HOST"] = "tenant-a.localhost"
    return client


@pytest.mark.django_db
class TestShareLedgerListView:
    def test_owner_can_list_ledger(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with schema_context(tenant_a.schema_name):
            owner = StaffUserFactory(role=Role.OWNER)
            partner = ReferralPartnerFactory(name="Dr. Tariq")
            rule = RevenueShareRuleFactory(
                referral_partner=partner, percent=Decimal("15.00")
            )
            payment = PaymentFactory()
            entry = ShareLedgerEntryFactory(
                referral_partner=partner,
                rule=rule,
                payment=payment,
                amount=Decimal("150.00"),
                percent_applied=Decimal("15.00"),
                basis_amount=Decimal("1000.00"),
                period="2026-10",
            )

            _auth(api_client, owner, tenant_a, role=Role.OWNER)
            resp = api_client.get("/api/v1/referral-partners/ledger")

            assert resp.status_code == 200
            data = resp.json()
            assert "results" in data
            assert "totals" in data
            assert data["totals"]["count"] >= 1
            assert Decimal(data["totals"]["amount"]) >= Decimal("150.00")

            row = next(r for r in data["results"] if r["id"] == str(entry.id))
            assert row["referral_partner_name"] == "Dr. Tariq"
            assert row["amount"] == "150.00"
            assert row["percent_applied"] == "15.00"
            assert row["rule_percent"] == "15.00"
            assert row["period"] == "2026-10"
            assert row["settlement"] is None

    def test_manager_can_list_ledger(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with schema_context(tenant_a.schema_name):
            manager = StaffUserFactory(role=Role.MANAGER)
            _auth(api_client, manager, tenant_a, role=Role.MANAGER)
            resp = api_client.get("/api/v1/referral-partners/ledger")
            assert resp.status_code == 200

    def test_receptionist_forbidden_403(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with schema_context(tenant_a.schema_name):
            receptionist = StaffUserFactory(role=Role.RECEPTION)
            _auth(api_client, receptionist, tenant_a, role=Role.RECEPTION)
            resp = api_client.get("/api/v1/referral-partners/ledger")
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "forbidden"

    def test_unauthenticated_401(self, tenant_a: Tenant, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/referral-partners/ledger")
        assert resp.status_code == 401

    def test_filter_by_partner_and_period(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with schema_context(tenant_a.schema_name):
            owner = StaffUserFactory(role=Role.OWNER)
            p1 = ReferralPartnerFactory(name="Partner 1")
            p2 = ReferralPartnerFactory(name="Partner 2")

            e1 = ShareLedgerEntryFactory(
                referral_partner=p1,
                payment=PaymentFactory(),
                amount=Decimal("100.00"),
                period="2026-09",
            )
            e2 = ShareLedgerEntryFactory(
                referral_partner=p2,
                payment=PaymentFactory(),
                amount=Decimal("200.00"),
                period="2026-10",
            )

            _auth(api_client, owner, tenant_a)

            # Filter by partner 1
            resp = api_client.get(
                f"/api/v1/referral-partners/ledger?partner_id={p1.id}"
            )
            assert resp.status_code == 200
            data = resp.json()
            ids = [r["id"] for r in data["results"]]
            assert str(e1.id) in ids
            assert str(e2.id) not in ids
            assert data["totals"]["count"] == 1
            assert data["totals"]["amount"] == "100.00"

            # Filter by period 2026-10
            resp_period = api_client.get(
                "/api/v1/referral-partners/ledger?period=2026-10"
            )
            assert resp_period.status_code == 200
            ids_period = [r["id"] for r in resp_period.json()["results"]]
            assert str(e2.id) in ids_period
            assert str(e1.id) not in ids_period

    def test_filter_validation_errors_422(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with schema_context(tenant_a.schema_name):
            owner = StaffUserFactory(role=Role.OWNER)
            _auth(api_client, owner, tenant_a)

            # Invalid partner_id
            resp = api_client.get(
                "/api/v1/referral-partners/ledger?partner_id=not-a-uuid"
            )
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "validation_error"

            # Invalid period format
            resp_p = api_client.get("/api/v1/referral-partners/ledger?period=2026-9")
            assert resp_p.status_code == 422
            assert resp_p.json()["error"]["code"] == "validation_error"

            # Invalid cursor
            resp_c = api_client.get(
                "/api/v1/referral-partners/ledger?cursor=invalid-uuid"
            )
            assert resp_c.status_code == 422
            assert resp_c.json()["error"]["code"] == "validation_error"

    def test_settlement_join_active_vs_cancelled(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with schema_context(tenant_a.schema_name):
            owner = StaffUserFactory(role=Role.OWNER)
            partner = ReferralPartnerFactory()

            # Entry 1 in active APPROVED settlement
            e1 = ShareLedgerEntryFactory(
                referral_partner=partner,
                payment=PaymentFactory(),
                amount=Decimal("300.00"),
                period="2026-10",
            )
            s_approved = SettlementFactory(
                referral_partner=partner,
                period="2026-10",
                status=Settlement.Status.APPROVED,
            )
            SettlementLineFactory(settlement=s_approved, share_ledger_entry=e1)

            # Entry 2 in CANCELLED settlement -> settlement object should be null
            e2 = ShareLedgerEntryFactory(
                referral_partner=partner,
                payment=PaymentFactory(),
                amount=Decimal("400.00"),
                period="2026-09",
            )
            s_cancelled = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.CANCELLED,
            )
            SettlementLineFactory(settlement=s_cancelled, share_ledger_entry=e2)

            _auth(api_client, owner, tenant_a)
            resp = api_client.get(
                f"/api/v1/referral-partners/ledger?partner_id={partner.id}"
            )
            assert resp.status_code == 200
            data = resp.json()

            row1 = next(r for r in data["results"] if r["id"] == str(e1.id))
            assert row1["settlement"] is not None
            assert row1["settlement"]["id"] == str(s_approved.id)
            assert row1["settlement"]["status"] == "APPROVED"

            row2 = next(r for r in data["results"] if r["id"] == str(e2.id))
            assert row2["settlement"] is None
