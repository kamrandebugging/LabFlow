"""LAB-43 (KAN-262 / LAB-65): Full monthly cycle rehearsal test.

Doc 05 §12.8, §13.2 — exercises the whole money pipeline end to end:
payments -> ledger -> Beat generation -> Owner approve -> PDF ->
stub delivery -> mark-paid. Drafts badge updates on /exceptions.

Uses the on-main models directly (settlement generation/approval/PDF live
in sibling LAB-41/42/44 branches); the delivery leg is this LAB's code,
run in SETTLEMENT_DELIVERY_STUB mode so no n8n is needed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client, override_settings
from django_tenants.utils import schema_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role, StaffUser
from apps.core.models import Tenant
from apps.notifications.models import Notification
from apps.partners.delivery import dispatch_settlement_delivery
from apps.partners.models import (
    ReferralPartner,
    Settlement,
    SettlementLine,
)
from tests.factories.accounts import StaffUserFactory
from tests.factories.branches import BranchFactory
from tests.factories.partners import (
    ReferralPartnerFactory,
    RevenueShareRuleFactory,
    SettlementFactory,
    ShareLedgerEntryFactory,
)


def _make_settlement(partner: ReferralPartner, **kwargs: Any) -> Settlement:
    """Typed wrapper: factory_boy stubs return the factory type."""
    return cast(
        Settlement,
        SettlementFactory(referral_partner=partner, **kwargs),
    )


def _make_partner(**kwargs: Any) -> ReferralPartner:
    """Typed wrapper: factory_boy stubs return the factory type."""
    return cast(ReferralPartner, ReferralPartnerFactory(**kwargs))


def _auth_headers(user: StaffUser, tenant_id: str = "tenant_a") -> dict[str, str]:
    session = AuthService.create_session(user=user, tenant_id=tenant_id)
    slug = tenant_id.replace("_", "-")
    return {
        "Authorization": f"Bearer {session['access']}",
        "Host": f"{slug}.localhost",
    }


def _get(client: Client, user: StaffUser, url: str) -> Any:
    return client.get(url, headers=_auth_headers(user))


@pytest.mark.django_db
class TestMonthlyCycleRehearsal:
    """LAB-65: one tenant, one partner, one period — the whole loop."""

    @pytest.fixture(autouse=True)
    def _stub_delivery(self) -> Any:
        # SETTLEMENT_DELIVERY_STUB is a plain pytest class here, so apply
        # the override as a context manager rather than a decorator.
        with override_settings(SETTLEMENT_DELIVERY_STUB=True):
            yield

    def test_full_cycle_payments_to_paid(self, tenant_a: Tenant) -> None:
        client = Client()
        period = "2026-10"
        with schema_context(tenant_a.schema_name):
            branch = BranchFactory()
            owner = cast(StaffUser, StaffUserFactory(branch=branch, role=Role.OWNER))
            partner = _make_partner(email="rehearsal@example.com")
            rule = RevenueShareRuleFactory(referral_partner=partner)

            # 1. Ledger: two attributed payments land as ledger rows.
            e1 = ShareLedgerEntryFactory(
                referral_partner=partner,
                rule=rule,
                amount=Decimal("200.00"),
                period=period,
            )
            e2 = ShareLedgerEntryFactory(
                referral_partner=partner,
                rule=rule,
                amount=Decimal("300.00"),
                period=period,
            )

            # 2. Beat generation: draft the settlement from pending entries.
            settlement = Settlement.objects.create(
                referral_partner=partner,
                period=period,
                status=Settlement.Status.DRAFT,
                total=Decimal("500.00"),
            )
            for entry in (e1, e2):
                SettlementLine.objects.create(
                    settlement=settlement,
                    share_ledger_entry=entry,
                    amount=entry.amount,
                )

            # Drafts badge sees it.
            resp = _get(client, owner, "/api/v1/settlements/exceptions")
            assert resp.status_code == 200
            assert resp.json()["drafts_awaiting_approval"] == 1

            # 3. Owner approves.
            settlement.status = Settlement.Status.APPROVED
            settlement.approved_by = owner
            settlement.save(update_fields=["status", "approved_by", "updated_at"])

            # 4. Statement PDF rendered (stub bytes stand in for LAB-44's PDF).
            pdf_key = f"settlements/{settlement.id}/statement.pdf"
            pdf_bytes = b"%PDF-1.4 rehearsal statement"
            default_storage.save(pdf_key, ContentFile(pdf_bytes))
            settlement.statement_pdf_key = pdf_key
            settlement.save(update_fields=["statement_pdf_key", "updated_at"])

            # 5. Stub delivery: dispatch + immediate callback-equivalent.
            try:
                notif = dispatch_settlement_delivery(settlement, actor=owner)
                # Stub mode marks SENT synchronously through the callback path.
                notif.refresh_from_db()
                assert notif.status == Notification.Status.SENT
                settlement.refresh_from_db()
                assert settlement.status == Settlement.Status.SENT

                # 6. Mark paid.
                settlement.status = Settlement.Status.PAID
                settlement.save(update_fields=["status", "updated_at"])

                # Badge clears: no drafts, no failed deliveries.
                resp = _get(client, owner, "/api/v1/settlements/exceptions")
                assert resp.status_code == 200
                data = resp.json()
                assert data["drafts_awaiting_approval"] == 0
                assert data["failed_deliveries"] == 0

                # Money is intact end to end.
                settlement.refresh_from_db()
                assert settlement.total == Decimal("500.00")
                assert settlement.status == Settlement.Status.PAID
            finally:
                if default_storage.exists(pdf_key):
                    default_storage.delete(pdf_key)

    def test_rehearsal_delivery_failure_keeps_money_safe(
        self, tenant_a: Tenant
    ) -> None:
        """RS-41 in rehearsal form: email-less partner, money untouched."""
        with schema_context(tenant_a.schema_name):
            branch = BranchFactory()
            owner = cast(StaffUser, StaffUserFactory(branch=branch, role=Role.OWNER))
            partner = _make_partner(email=None)
            rule = RevenueShareRuleFactory(referral_partner=partner)
            ShareLedgerEntryFactory(
                referral_partner=partner,
                rule=rule,
                amount=Decimal("150.00"),
                period="2026-10",
            )
            settlement = _make_settlement(
                partner,
                status=Settlement.Status.APPROVED,
                total=Decimal("150.00"),
            )

            notif = dispatch_settlement_delivery(settlement, actor=owner)

            assert notif.status == Notification.Status.FAILED
            assert notif.last_error == "partner_email_missing"
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.APPROVED
            assert settlement.total == Decimal("150.00")
