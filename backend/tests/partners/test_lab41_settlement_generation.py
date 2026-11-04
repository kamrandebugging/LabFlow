"""LAB-41 (KAN-260): Monthly settlement generation tests.

Doc 05 §7.2 (ST-1–ST-8): generation, draft lifecycle, idempotency.
Doc 05 §7.4 (ST-9–ST-12): approval + finalize.
Doc 05 §8.2: statement layout.
Doc 05 §12.5 (CF-1–CF-4): late entries.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django_tenants.utils import tenant_context

from apps.partners.models import Settlement
from apps.partners.settlement_service import (
    build_statement_context,
    draft_partner_settlement,
    previous_period,
    select_draft_entries,
)
from tests.factories.partners import (
    ReferralPartnerFactory,
    SettlementFactory,
    SettlementLineFactory,
    ShareLedgerEntryFactory,
)


@pytest.mark.django_db
class TestPreviousPeriod:
    def test_october_maps_to_september(self) -> None:
        assert previous_period(date(2026, 10, 1)) == "2026-09"

    def test_january_rolls_back_year(self) -> None:
        assert previous_period(date(2026, 1, 15)) == "2025-12"


@pytest.mark.django_db
class TestSelectDraftEntries:
    """Doc 05 §7.2 ST-3, §12.5 CF-4."""

    def test_selects_pending_entries_for_target_period(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            e1 = ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("100.00")
            )
            e2 = ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("50.00")
            )
            selected = select_draft_entries(partner.id, "2026-09")
            assert {e.id for e in selected} == {e1.id, e2.id}

    def test_excludes_entries_already_on_live_settlement(self, tenant_a: Any) -> None:
        """Derived status settled: a line on a DRAFT settlement is in-draft."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            entry = ShareLedgerEntryFactory(referral_partner=partner, period="2026-09")
            settlement = SettlementFactory(referral_partner=partner, period="2026-09")
            SettlementLineFactory(settlement=settlement, share_ledger_entry=entry)
            assert select_draft_entries(partner.id, "2026-09") == []

    def test_cancelled_settlement_line_does_not_count(self, tenant_a: Any) -> None:
        """Doc 05 §6.7: a line on a CANCELLED settlement is pending again."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            entry = ShareLedgerEntryFactory(referral_partner=partner, period="2026-09")
            settlement = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.CANCELLED,
            )
            SettlementLineFactory(settlement=settlement, share_ledger_entry=entry)
            selected = select_draft_entries(partner.id, "2026-09")
            assert [e.id for e in selected] == [entry.id]

    def test_late_entry_from_closed_period_is_selected(self, tenant_a: Any) -> None:
        """Doc 05 §12.5 CF-3/CF-4: pending entry from an earlier closed
        period joins the current draft."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            # August settlement is APPROVED (closed).
            SettlementFactory(
                referral_partner=partner,
                period="2026-08",
                status=Settlement.Status.APPROVED,
            )
            late = ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-08", amount=Decimal("75.00")
            )
            current = ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("25.00")
            )
            selected = select_draft_entries(partner.id, "2026-09")
            assert {e.id for e in selected} == {late.id, current.id}

    def test_late_entry_blocked_by_open_draft(self, tenant_a: Any) -> None:
        """Doc 05 §12.5 CF-2: if the entry's period settlement is still
        DRAFT, the entry stays pending until cancel + re-draft."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            SettlementFactory(
                referral_partner=partner,
                period="2026-08",
                status=Settlement.Status.DRAFT,
            )
            late = ShareLedgerEntryFactory(referral_partner=partner, period="2026-08")
            assert late.id not in {
                e.id for e in select_draft_entries(partner.id, "2026-09")
            }


@pytest.mark.django_db
class TestDraftPartnerSettlement:
    """Doc 05 §7.2 ST-4–ST-7."""

    def test_draft_creates_settlement_and_lines(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("100.00")
            )
            ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("50.00")
            )
            result = draft_partner_settlement(partner.id, "2026-09")
            assert result["status"] == "drafted"
            settlement = Settlement.objects.get(id=result["settlement_id"])
            assert settlement.status == Settlement.Status.DRAFT
            assert settlement.total == Decimal("150.00")
            assert settlement.lines.count() == 2

    def test_no_entries_means_no_settlement(self, tenant_a: Any) -> None:
        """Doc 05 ST-5: no empty settlements."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            result = draft_partner_settlement(partner.id, "2026-09")
            assert result["status"] == "no_entries"
            assert (
                Settlement.objects.filter(
                    referral_partner=partner, period="2026-09"
                ).count()
                == 0
            )

    def test_negative_total_still_drafted(self, tenant_a: Any) -> None:
        """Doc 05 ST-6: negative totals are drafted, not hidden."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("-80.00")
            )
            ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("30.00")
            )
            result = draft_partner_settlement(partner.id, "2026-09")
            assert result["status"] == "drafted"
            settlement = Settlement.objects.get(id=result["settlement_id"])
            assert settlement.total == Decimal("-50.00")

    def test_redraft_is_noop_when_live_settlement_exists(self, tenant_a: Any) -> None:
        """Doc 05 ST-7: idempotent — the partial unique index refuses a
        second live row; the task treats it as already drafted."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            ShareLedgerEntryFactory(referral_partner=partner, period="2026-09")
            first = draft_partner_settlement(partner.id, "2026-09")
            assert first["status"] == "drafted"
            # New entry arrives; re-run must not create a second settlement.
            ShareLedgerEntryFactory(referral_partner=partner, period="2026-09")
            second = draft_partner_settlement(partner.id, "2026-09")
            assert second["status"] == "already_drafted"
            assert (
                Settlement.objects.filter(referral_partner=partner, period="2026-09")
                .exclude(status=Settlement.Status.CANCELLED)
                .count()
                == 1
            )

    def test_redraft_after_cancel_creates_new_row(self, tenant_a: Any) -> None:
        """Doc 05 §7.6 ST-19: after cancellation, re-draft inserts a new row."""
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            ShareLedgerEntryFactory(referral_partner=partner, period="2026-09")
            first = draft_partner_settlement(partner.id, "2026-09")
            settlement = Settlement.objects.get(id=first["settlement_id"])
            settlement.status = Settlement.Status.CANCELLED
            settlement.save(update_fields=["status"])
            second = draft_partner_settlement(partner.id, "2026-09")
            assert second["status"] == "drafted"
            assert second["settlement_id"] != first["settlement_id"]


@pytest.mark.django_db
class TestBuildStatementContext:
    """Doc 05 §8.2 layout."""

    def test_context_has_all_sections(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory(
                name="Dr. Test", organisation="Test Clinic"
            )
            entry = ShareLedgerEntryFactory(
                referral_partner=partner,
                period="2026-09",
                amount=Decimal("200.00"),
                basis_amount=Decimal("1000.00"),
                percent_applied=Decimal("20.00"),
            )
            settlement = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.APPROVED,
                total=Decimal("200.00"),
            )
            SettlementLineFactory(
                settlement=settlement,
                share_ledger_entry=entry,
                amount=Decimal("200.00"),
            )
            ctx = build_statement_context(settlement.id)
            assert ctx["statement_id"] == str(settlement.id)
            assert ctx["period"] == "2026-09"
            assert ctx["period_label"] == "September 2026"
            assert ctx["currency"] == "PKR"
            assert ctx["partner_name"] == "Dr. Test"
            assert ctx["total"] == "200.00"
            assert len(ctx["lines"]) == 1
            line = ctx["lines"][0]
            assert line["basis_amount"] == "1000.00"
            assert line["percent_applied"] == "20.00"
            assert line["amount"] == "200.00"
            # Single period: no subtotals.
            assert ctx["subtotals"] == []

    def test_multi_period_subtotals(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            e1 = ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-08", amount=Decimal("75.00")
            )
            e2 = ShareLedgerEntryFactory(
                referral_partner=partner, period="2026-09", amount=Decimal("25.00")
            )
            settlement = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.APPROVED,
                total=Decimal("100.00"),
            )
            SettlementLineFactory(
                settlement=settlement, share_ledger_entry=e1, amount=Decimal("75.00")
            )
            SettlementLineFactory(
                settlement=settlement, share_ledger_entry=e2, amount=Decimal("25.00")
            )
            ctx = build_statement_context(settlement.id)
            assert len(ctx["subtotals"]) == 2
            by_period = {s["period"]: s["subtotal"] for s in ctx["subtotals"]}
            assert by_period == {"2026-08": "75.00", "2026-09": "25.00"}

    def test_negative_total_flag(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            settlement = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.APPROVED,
                total=Decimal("-50.00"),
            )
            ctx = build_statement_context(settlement.id)
            assert ctx["is_negative"] is True
            assert ctx["total"] == "-50.00"


@pytest.mark.django_db
class TestRenderStatementPdf:
    def test_pdf_renders(self, tenant_a: Any) -> None:
        pytest.importorskip("weasyprint")
        from apps.partners.statement_pdf import render_statement_pdf

        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            settlement = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.APPROVED,
                total=Decimal("200.00"),
            )
            ctx = build_statement_context(settlement.id)
            pdf = render_statement_pdf(ctx)
            assert pdf[:5] == b"%PDF-"
