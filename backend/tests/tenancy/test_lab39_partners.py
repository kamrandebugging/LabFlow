"""LAB-39 Test Suite: Referral partner registry + revenue-share rules
(Doc 05 §5.1–§5.4, §10, §12.5; KAN-164; original LAB-56 + LAB-57).
Backend only.

Part 1 — Partner CRUD (RP-1..RP-6, RS-38):
- Owner-only on all endpoints; other roles -> 403.
- POST requires Idempotency-Key; replay -> 200 original; key reuse ->
  409 idempotency_key_reused.
- name required; bad email -> 422 validation_error; unknown fields -> 422.
- PATCH edits identity fields; audit row per mutation.
- DELETE soft-deletes; 409 partner_has_ledger_entries when ledger rows
  exist (RS-38); deleted partner -> 404.

Part 2 — Rule CRUD + specificity (RR-1..RR-13, RS-01..RS-08, RS-13, RS-14):
- RS-01: same-bucket overlap -> 422 rule_overlap, nothing written.
- RS-02: different-bucket overlap -> both accepted.
- RS-03/04/05: specificity order via resolve_rule (bucket 1 wins; branch
  beats category; general rate).
- RS-06: no rules -> None (0% fallback, never errors).
- RS-07: future rule -> not applying today.
- RS-08: PATCH closes old (effective_to set) + inserts new; old
  percent/effective_from untouched.
- RS-13/14: category matching is all-or-nothing per invoice.
- RR-4: retroactive edit -> 422 rule_retroactive.
- percent outside 0..100 -> 422; unknown branch -> 404.

Part 3 — Dashboard (§10, §12.5):
- Owner only; YTD earned/settled, pending total, last 6 settlements,
  late_entries count, has_email — computed at read time.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.partners.models import (
    ReferralPartner,
    RevenueShareRule,
    Settlement,
)
from apps.partners.services import resolve_rule
from tests.factories.branch import BranchFactory
from tests.factories.partners import (
    ReferralPartnerFactory,
    RevenueShareRuleFactory,
    SettlementFactory,
    SettlementLineFactory,
    ShareLedgerEntryFactory,
)
from tests.factories.staff_user import StaffUserFactory

KARACHI = ZoneInfo("Asia/Karachi")
PARTNERS_URL = "/api/v1/referral-partners"
TODAY = date(2026, 11, 3)


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser | None = None, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        headers = {"Host": f"{slug}.localhost"}
        if staff_user is not None:
            session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
            headers["Authorization"] = f"Bearer {session['access']}"
        return headers

    return _make_headers


@pytest.fixture
def lab39_setup(tenant_a: Any) -> dict[str, Any]:
    """Owner + one user per other role, inside tenant_a."""
    with tenant_context(tenant_a):
        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="o39@labflow.app")
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=None, email="m39@labflow.app"
        )
        reception = StaffUserFactory(
            role=Role.RECEPTION, branch=None, email="r39@labflow.app"
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=None, email="t39@labflow.app"
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=None, email="p39@labflow.app"
        )
        return {
            "owner": owner,
            "manager": manager,
            "reception": reception,
            "technician": technician,
            "pathologist": pathologist,
        }


def _client_kwargs(headers: dict[str, str], key: str | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"HTTP_HOST": headers["Host"]}
    if "Authorization" in headers:
        kwargs["HTTP_AUTHORIZATION"] = headers["Authorization"]
    if key is not None:
        kwargs["HTTP_IDEMPOTENCY_KEY"] = key
    return kwargs


def _post_partner(
    client: Client,
    headers: dict[str, str],
    payload: dict[str, Any],
    key: str | None = "k-1",
) -> Any:
    import json

    return client.post(
        PARTNERS_URL,
        data=json.dumps(payload),
        content_type="application/json",
        **_client_kwargs(headers, key),
    )


def _api_get(client: Client, headers: dict[str, str], url: str) -> Any:
    return client.get(url, **_client_kwargs(headers))


def _api_patch(
    client: Client, headers: dict[str, str], url: str, payload: dict[str, Any]
) -> Any:
    import json

    return client.patch(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **_client_kwargs(headers),
    )


def _api_delete(client: Client, headers: dict[str, str], url: str) -> Any:
    return client.delete(url, **_client_kwargs(headers))


# ---------------------------------------------------------------------------
# Part 1 — Partner CRUD
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPartnerCrud:
    def test_owner_create_201(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        resp = _post_partner(
            c, h, {"name": "Dr. Ahmed", "email": "ahmed@clinic.pk"}, key="k-create-1"
        )
        assert resp.status_code == 201, resp.content[:400]
        body = resp.json()
        assert body["name"] == "Dr. Ahmed"
        assert body["is_active"] is True
        with tenant_context(tenant_a):
            assert (
                AuditLog.objects.filter(
                    action="partner.created", entity_type="referral_partner"
                ).count()
                == 1
            )

    def test_non_owner_forbidden(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        for role in ("manager", "reception", "technician", "pathologist"):
            h = auth_headers(lab39_setup[role])
            resp = _post_partner(c, h, {"name": "Dr. X"}, key=f"k-forbid-{role}")
            assert resp.status_code == 403, (role, resp.content[:200])
            resp = _api_get(c, h, PARTNERS_URL)
            assert resp.status_code == 403, (role, resp.content[:200])

    def test_missing_idempotency_key_422(
        self, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        resp = _post_partner(
            c, auth_headers(lab39_setup["owner"]), {"name": "Dr. Y"}, key=None
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "idempotency_key_required"

    def test_name_required_and_bad_email_422(
        self, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        resp = _post_partner(c, h, {"email": "a@b.pk"}, key="k-noname")
        assert resp.status_code == 422
        resp = _post_partner(
            c, h, {"name": "Dr. Z", "email": "not-an-email"}, key="k-bademail"
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_unknown_field_rejected(
        self, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        resp = _post_partner(
            c,
            auth_headers(lab39_setup["owner"]),
            {"name": "Dr. U", "hack": "1"},
            key="k-unknown",
        )
        assert resp.status_code == 422

    def test_idempotent_replay_returns_original(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        payload = {"name": "Dr. Replay", "phone": "+923001234567"}
        r1 = _post_partner(c, h, payload, key="k-replay")
        r2 = _post_partner(c, h, payload, key="k-replay")
        assert r1.status_code == 201
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]
        with tenant_context(tenant_a):
            assert ReferralPartner.objects.filter(deleted_at__isnull=True).count() == 1

    def test_idempotency_key_reused_409(
        self, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        r1 = _post_partner(c, h, {"name": "Dr. Same"}, key="k-reuse")
        r2 = _post_partner(c, h, {"name": "Dr. Different"}, key="k-reuse")
        assert r1.status_code == 201
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "idempotency_key_reused"

    def test_list_excludes_deleted(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            ReferralPartnerFactory(name="Live Partner")
            dead = ReferralPartnerFactory(name="Dead Partner")
            owner = lab39_setup["owner"]
            from apps.partners.services import PartnerService

            PartnerService.delete_partner(owner, dead.id)
        resp = _api_get(c, h, PARTNERS_URL)
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()["results"]]
        assert "Live Partner" in names
        assert "Dead Partner" not in names
        # deleted partner detail -> 404
        resp = _api_get(c, h, f"{PARTNERS_URL}/{dead.id}")
        assert resp.status_code == 404

    def test_patch_updates_and_audits(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory(name="Old Name", is_active=True)
        resp = _api_patch(
            c,
            h,
            f"{PARTNERS_URL}/{partner.id}",
            {"name": "New Name", "is_active": False},
        )
        assert resp.status_code == 200, resp.content[:300]
        body = resp.json()
        assert body["name"] == "New Name"
        assert body["is_active"] is False
        with tenant_context(tenant_a):
            assert (
                AuditLog.objects.filter(
                    action="partner.updated", entity_id=partner.id
                ).count()
                == 1
            )

    def test_delete_with_ledger_entries_409_rs38(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """RS-38: soft-delete refused while ledger rows point at the partner."""
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            ShareLedgerEntryFactory(referral_partner=partner)
        resp = _api_delete(c, h, f"{PARTNERS_URL}/{partner.id}")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "partner_has_ledger_entries"

    def test_delete_without_history_204(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """RS-38: a partner with no ledger rows soft-deletes cleanly."""
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            pid = partner.id
        resp = _api_delete(c, h, f"{PARTNERS_URL}/{pid}")
        assert resp.status_code == 204
        with tenant_context(tenant_a):
            partner.refresh_from_db()
            assert partner.deleted_at is not None
            assert (
                AuditLog.objects.filter(action="partner.deleted", entity_id=pid).count()
                == 1
            )


# ---------------------------------------------------------------------------
# Part 2 — Rules: overlap, specificity, edit
# ---------------------------------------------------------------------------


def _post_rule(
    client: Client,
    headers: dict[str, str],
    partner_id: uuid.UUID,
    payload: dict[str, Any],
) -> Any:
    import json

    return client.post(
        f"{PARTNERS_URL}/{partner_id}/rules",
        data=json.dumps(payload),
        content_type="application/json",
        **_client_kwargs(headers),
    )


@pytest.mark.django_db
class TestRuleCrud:
    def test_rs01_same_bucket_overlap_422(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
        p1 = {
            "branch_id": str(branch.id),
            "test_category": "Hematology",
            "percent": "10.00",
            "effective_from": "2026-01-01",
        }
        r1 = _post_rule(c, h, partner.id, p1)
        assert r1.status_code == 201, r1.content[:300]
        r2 = _post_rule(c, h, partner.id, p1)
        assert r2.status_code == 422
        assert r2.json()["error"]["code"] == "rule_overlap"
        with tenant_context(tenant_a):
            assert (
                RevenueShareRule.objects.filter(referral_partner_id=partner.id).count()
                == 1
            )  # nothing written

    def test_rs02_different_buckets_accepted(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
        base = {
            "percent": "10.00",
            "effective_from": "2026-01-01",
        }
        r1 = _post_rule(c, h, partner.id, {**base, "branch_id": str(branch.id)})
        r2 = _post_rule(c, h, partner.id, {**base, "test_category": "Hematology"})
        assert r1.status_code == 201, r1.content[:300]
        assert r2.status_code == 201, r2.content[:300]

    def test_rs03_specificity_bucket1_wins(
        self, tenant_a: Any, lab39_setup: dict[str, Any]
    ) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category=None,
                percent=Decimal("5.00"),
                effective_from=date(2026, 1, 1),
            )
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=branch,
                test_category="Hematology",
                percent=Decimal("20.00"),
                effective_from=date(2026, 1, 1),
            )
            rule = resolve_rule(partner.id, branch.id, ["Hematology"], TODAY)
            assert rule is not None
            assert rule.percent == Decimal("20.00")

    def test_rs04_branch_beats_category(
        self, tenant_a: Any, lab39_setup: dict[str, Any]
    ) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category="Hematology",
                percent=Decimal("15.00"),
                effective_from=date(2026, 1, 1),
            )
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=branch,
                test_category=None,
                percent=Decimal("12.00"),
                effective_from=date(2026, 1, 1),
            )
            rule = resolve_rule(partner.id, branch.id, ["Hematology"], TODAY)
            assert rule is not None
            assert rule.percent == Decimal("12.00")

    def test_rs05_only_general_rate(
        self, tenant_a: Any, lab39_setup: dict[str, Any]
    ) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category=None,
                percent=Decimal("7.50"),
                effective_from=date(2026, 1, 1),
            )
            rule = resolve_rule(partner.id, branch.id, ["Hematology"], TODAY)
            assert rule is not None
            assert rule.percent == Decimal("7.50")

    def test_rs06_no_rules_returns_none(
        self, tenant_a: Any, lab39_setup: dict[str, Any]
    ) -> None:
        """RR-11: resolution never errors; 0% fallback lives in resolution."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            assert resolve_rule(partner.id, branch.id, ["Hematology"], TODAY) is None

    def test_rs07_future_rule_not_applying(
        self, tenant_a: Any, lab39_setup: dict[str, Any]
    ) -> None:
        """RR-13: a rule starting next month earns nothing this month."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category=None,
                percent=Decimal("10.00"),
                effective_from=date(2026, 12, 1),
            )
            assert resolve_rule(partner.id, branch.id, [], TODAY) is None
            assert (
                resolve_rule(partner.id, branch.id, [], date(2026, 12, 15)) is not None
            )

    def test_rs08_patch_closes_old_inserts_new(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            rule = RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category=None,
                percent=Decimal("10.00"),
                effective_from=date(2026, 1, 1),
            )
            rid = rule.id
        resp = _api_patch(
            c,
            h,
            f"/api/v1/revenue-share-rules/{rid}",
            {"percent": "12.00", "effective_from": "2026-06-01"},
        )
        assert resp.status_code == 200, resp.content[:400]
        body = resp.json()
        assert body["percent"] == "12.00"
        assert body["effective_from"] == "2026-06-01"
        assert body["id"] != str(rid)
        with tenant_context(tenant_a):
            old = RevenueShareRule.objects.get(id=rid)
            # old row's percent and effective_from untouched; only closed
            assert old.percent == Decimal("10.00")
            assert old.effective_from == date(2026, 1, 1)
            assert old.effective_to == date(2026, 5, 31)
            assert (
                RevenueShareRule.objects.filter(referral_partner_id=partner.id).count()
                == 2
            )
            assert AuditLog.objects.filter(action="rule.updated").count() == 1

    def test_rs13_mixed_category_ignores_category_rule(
        self, tenant_a: Any, lab39_setup: dict[str, Any]
    ) -> None:
        """RR-10: mixed-category invoice -> only NULL-category buckets."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category="Hematology",
                percent=Decimal("25.00"),
                effective_from=date(2026, 1, 1),
            )
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category=None,
                percent=Decimal("8.00"),
                effective_from=date(2026, 1, 1),
            )
            rule = resolve_rule(
                partner.id, branch.id, ["Hematology", "Biochemistry"], TODAY
            )
            assert rule is not None
            assert rule.percent == Decimal("8.00")

    def test_rs14_single_category_matches(
        self, tenant_a: Any, lab39_setup: dict[str, Any]
    ) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            RevenueShareRuleFactory(
                referral_partner=partner,
                branch=None,
                test_category="Hematology",
                percent=Decimal("25.00"),
                effective_from=date(2026, 1, 1),
            )
            rule = resolve_rule(partner.id, branch.id, ["Hematology"], TODAY)
            assert rule is not None
            assert rule.percent == Decimal("25.00")

    def test_patch_closed_rule_requires_adjacent_start(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """RR-4: PATCH on an already-closed rule must continue exactly the
        day after its effective_to — no gaps, no retroactive extension."""
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            rule = RevenueShareRuleFactory(
                referral_partner=partner,
                percent=Decimal("10.00"),
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 5, 31),
            )
            rid = rule.id
        # Gap -> rejected
        resp = c.patch(
            f"/api/v1/revenue-share-rules/{rid}",
            data={"percent": "12.00", "effective_from": "2026-08-01"},
            content_type="application/json",
            **_client_kwargs(h),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "rule_retroactive"
        # Adjacent -> accepted, old end date untouched
        resp = _api_patch(
            c,
            h,
            f"/api/v1/revenue-share-rules/{rid}",
            {"percent": "12.00", "effective_from": "2026-06-01"},
        )
        assert resp.status_code == 200, resp.content[:300]
        with tenant_context(tenant_a):
            old = RevenueShareRule.objects.get(id=rid)
            assert old.effective_to == date(2026, 5, 31)

    def test_retroactive_edit_rejected(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """RR-4: no retroactive rule edits."""
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            rule = RevenueShareRuleFactory(
                referral_partner=partner,
                percent=Decimal("10.00"),
                effective_from=date(2026, 6, 1),
            )
            rid = rule.id
        resp = _api_patch(
            c,
            h,
            f"/api/v1/revenue-share-rules/{rid}",
            {"percent": "15.00", "effective_from": "2026-01-01"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "rule_retroactive"

    def test_percent_bounds_and_unknown_branch(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
        bad = {
            "percent": "101.00",
            "effective_from": "2026-01-01",
        }
        resp = _post_rule(c, h, partner.id, bad)
        assert resp.status_code == 422
        resp = _post_rule(
            c,
            h,
            partner.id,
            {
                "percent": "10.00",
                "effective_from": "2026-01-01",
                "branch_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404

    def test_rule_endpoints_owner_only(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
        h = auth_headers(lab39_setup["manager"])
        resp = _api_get(c, h, f"{PARTNERS_URL}/{partner.id}/rules")
        assert resp.status_code == 403
        resp = _post_rule(
            c, h, partner.id, {"percent": "10.00", "effective_from": "2026-01-01"}
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Part 3 — Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDashboard:
    def _seed_ledger(
        self, tenant_a: Any, partner: Any, year: int = 2026
    ) -> dict[str, Any]:
        """Entries: 2 settled this year, 1 pending this year (late: period
        has a DRAFT settlement), 1 pending last year."""
        with tenant_context(tenant_a):
            e1 = ShareLedgerEntryFactory(
                referral_partner=partner,
                amount=Decimal("100.00"),
                period=f"{year}-09",
            )
            e2 = ShareLedgerEntryFactory(
                referral_partner=partner,
                amount=Decimal("200.00"),
                period=f"{year}-09",
            )
            e3 = ShareLedgerEntryFactory(
                referral_partner=partner,
                amount=Decimal("50.00"),
                period=f"{year}-10",
            )
            e4 = ShareLedgerEntryFactory(
                referral_partner=partner,
                amount=Decimal("75.00"),
                period=f"{year - 1}-12",
            )
            s1 = SettlementFactory(
                referral_partner=partner,
                period=f"{year}-09",
                status=Settlement.Status.APPROVED,
                total=Decimal("300.00"),
            )
            SettlementLineFactory(settlement=s1, share_ledger_entry=e1)
            SettlementLineFactory(settlement=s1, share_ledger_entry=e2)
            # DRAFT settlement for e3's period -> e3 counts as late
            SettlementFactory(
                referral_partner=partner,
                period=f"{year}-10",
                status=Settlement.Status.DRAFT,
                total=Decimal("0.00"),
            )
            return {"e3": e3, "e4": e4}

    def test_dashboard_figures(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        h = auth_headers(lab39_setup["owner"])
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory(email="has@mail.pk")
            self._seed_ledger(tenant_a, partner)
        resp = _api_get(c, h, f"{PARTNERS_URL}/{partner.id}/dashboard")
        assert resp.status_code == 200, resp.content[:400]
        body = resp.json()
        # YTD earned: all entries created this year (100+200+50+75)
        assert body["ytd_earned"] == "425.00"
        # YTD settled: 100+200 in the APPROVED settlement
        assert body["ytd_settled"] == "300.00"
        # pending: 50 + 75
        assert body["pending_total"] == "125.00"
        # late: e3 pending with a DRAFT settlement for 2026-10
        assert body["late_entries"] == 1
        assert body["has_email"] is True
        assert len(body["last_6_settlements"]) == 2
        assert body["last_6_settlements"][0]["period"] == "2026-10"

    def test_dashboard_owner_only_and_404(
        self, tenant_a: Any, lab39_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        c = Client()
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
        h = auth_headers(lab39_setup["manager"])
        resp = _api_get(c, h, f"{PARTNERS_URL}/{partner.id}/dashboard")
        assert resp.status_code == 403
        h = auth_headers(lab39_setup["owner"])
        resp = _api_get(c, h, f"{PARTNERS_URL}/{uuid.uuid4()}/dashboard")
        assert resp.status_code == 404
