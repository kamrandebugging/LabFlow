from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, models, transaction
from django_tenants.utils import schema_context

from apps.core.models import Tenant
from apps.partners.models import (
    Settlement,
    SettlementLine,
)
from tests.factories.accounts import StaffUserFactory
from tests.factories.partners import (
    ReferralPartnerFactory,
    SettlementFactory,
    SettlementLineFactory,
)


@pytest.mark.django_db
class TestSettlementAndSettlementLineModels:
    """
    Verifies KAN-67 (Doc 02 §5.8, §7, §8, §17, §18; Doc 05 §7):
    - settlement and settlement_line exist in tenant schemas only, never public.
    - Partial UNIQUE uq_settlement_partner_id_period on (referral_partner_id, period)
      WHERE status <> 'CANCELLED': blocks duplicate live settlements, allows
      re-draft after CANCELLED.
    - Database CHECK chk_settlement_status on ('DRAFT', 'APPROVED', 'SENT',
      'PAID', 'CANCELLED').
    - Database CHECK chk_settlement_period_format on ^\\d{4}-\\d{2}$.
    - UNIQUE uq_settlement_line_share_ledger_entry_id on
      settlement_line.share_ledger_entry_id.
    - settlement_line has created_at only (no updated_at).
    - All money columns are numeric(12,2), allowing negative totals/amounts.
    """

    def test_tables_exist_in_tenant_schema_and_not_public(
        self, tenant_a: Tenant
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('settlement', 'settlement_line')
                """
            )
            assert cursor.fetchall() == []

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name IN ('settlement', 'settlement_line')
                ORDER BY table_name
                """,
                [tenant_a.schema_name],
            )
            assert [r[0] for r in cursor.fetchall()] == [
                "settlement",
                "settlement_line",
            ]

    def test_columns_and_numeric_precision(self, tenant_a: Tenant) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    column_name,
                    data_type,
                    numeric_precision,
                    numeric_scale,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'settlement'
                """,
                [tenant_a.schema_name],
            )
            s_cols = {row[0]: row[1:] for row in cursor.fetchall()}

            cursor.execute(
                """
                SELECT
                    column_name,
                    data_type,
                    numeric_precision,
                    numeric_scale,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'settlement_line'
                """,
                [tenant_a.schema_name],
            )
            sl_cols = {row[0]: row[1:] for row in cursor.fetchall()}

        assert set(s_cols.keys()) == {
            "id",
            "referral_partner_id",
            "period",
            "status",
            "total",
            "statement_pdf_key",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        }
        assert s_cols["total"] == ("numeric", 12, 2, "NO")

        assert set(sl_cols.keys()) == {
            "id",
            "settlement_id",
            "share_ledger_entry_id",
            "amount",
            "created_at",
        }
        assert "updated_at" not in sl_cols
        assert "deleted_at" not in sl_cols
        assert sl_cols["amount"] == ("numeric", 12, 2, "NO")

    def test_partial_unique_allows_redraft_after_cancelled_and_blocks_second_live(
        self, tenant_a: Tenant
    ) -> None:
        with schema_context(tenant_a.schema_name):
            partner = ReferralPartnerFactory()
            s1 = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.CANCELLED,
            )
            assert s1.status == "CANCELLED"

            # A second CANCELLED settlement for the same partner + period is allowed
            s2 = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.CANCELLED,
            )
            assert s2.status == "CANCELLED"

            # Re-drafting a live (DRAFT) settlement for the same partner + period
            # succeeds
            live = SettlementFactory(
                referral_partner=partner,
                period="2026-09",
                status=Settlement.Status.DRAFT,
            )
            assert live.status == "DRAFT"

            # A second live settlement for the same partner + period fails at the DB
            for live_status in (
                Settlement.Status.DRAFT,
                Settlement.Status.APPROVED,
                Settlement.Status.SENT,
                Settlement.Status.PAID,
            ):
                with pytest.raises(IntegrityError), transaction.atomic():
                    Settlement.objects.create(
                        referral_partner=partner,
                        period="2026-09",
                        status=live_status,
                        total=Decimal("100.00"),
                    )

    @pytest.mark.parametrize(
        "valid_status",
        ["DRAFT", "APPROVED", "SENT", "PAID", "CANCELLED"],
    )
    def test_settlement_status_check_constraint_accepts_valid_values(
        self, tenant_a: Tenant, valid_status: str
    ) -> None:
        with schema_context(tenant_a.schema_name):
            s = SettlementFactory(status=valid_status)
            s.refresh_from_db()
            assert s.status == valid_status

    @pytest.mark.parametrize(
        "invalid_status",
        ["draft", "CANCELED", "PENDING", "VOID", ""],
    )
    def test_settlement_status_check_constraint_rejects_invalid_values(
        self, tenant_a: Tenant, invalid_status: str
    ) -> None:
        with schema_context(tenant_a.schema_name):
            partner = ReferralPartnerFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                Settlement.objects.create(
                    referral_partner=partner,
                    period="2026-10",
                    status=invalid_status,
                    total=Decimal("0.00"),
                )

    def test_settlement_line_unique_share_ledger_entry_id(
        self, tenant_a: Tenant
    ) -> None:
        with schema_context(tenant_a.schema_name):
            line = SettlementLineFactory()
            other_settlement = SettlementFactory(
                referral_partner=line.settlement.referral_partner,
                period="2026-11",
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                SettlementLine.objects.create(
                    settlement=other_settlement,
                    share_ledger_entry=line.share_ledger_entry,
                    amount=Decimal("200.00"),
                )

    def test_foreign_keys_protect_against_deletion(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            staff = StaffUserFactory()
            settlement = SettlementFactory(approved_by=staff)
            line = SettlementLineFactory(settlement=settlement)
            partner = settlement.referral_partner
            entry = line.share_ledger_entry

            with pytest.raises(models.ProtectedError):
                settlement.delete()

            with pytest.raises(models.ProtectedError):
                entry.delete()

            with pytest.raises(models.ProtectedError):
                staff.delete()

            with pytest.raises(models.ProtectedError):
                partner.delete()

    def test_indexes_exist_in_pg_indexes(self, tenant_a: Tenant) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s
                  AND tablename IN ('settlement', 'settlement_line')
                """,
                [tenant_a.schema_name],
            )
            index_names = {row[0] for row in cursor.fetchall()}

        assert "uq_settlement_partner_id_period" in index_names
        assert "idx_settlement_referral_partner_id" in index_names
        assert "idx_settlement_approved_by" in index_names
        assert "uq_settlement_line_share_ledger_entry_id" in index_names
        assert "idx_settlement_line_settlement_id" in index_names
        assert "idx_settlement_line_share_ledger_entry_id" in index_names
