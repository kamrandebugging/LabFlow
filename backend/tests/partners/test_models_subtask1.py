from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, models
from django_tenants.utils import schema_context

from apps.core.models import Tenant
from apps.partners.models import RevenueShareRule
from tests.factories.branches import BranchFactory
from tests.factories.partners import (
    ReferralPartnerFactory,
    RevenueShareRuleFactory,
)


@pytest.mark.django_db
class TestReferralPartnerAndRuleModels:
    """
    Verifies KAN-65 (Doc 02 §5.8, Doc 05 §5.1–§5.2):
    - referral_partner & revenue_share_rule table names, columns, types,
      nullability, defaults.
    - Database CHECK constraint chk_revenue_share_rule_percent_0_100
      (0 <= percent <= 100), including rejection of -1 and 101 via ORM and raw SQL.
    - Decimal precision numeric(5,2) (never float).
    - FK PROTECT (ON DELETE RESTRICT) on referral_partner_id and branch_id.
    - Explicit FK indexes idx_revenue_share_rule_referral_partner_id and
      idx_revenue_share_rule_branch_id.
    - Effective dating columns without any invented current-rule flag.
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
                  AND table_name IN ('referral_partner', 'revenue_share_rule')
                """
            )
            assert cursor.fetchall() == []

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name IN ('referral_partner', 'revenue_share_rule')
                ORDER BY table_name
                """,
                [tenant_a.schema_name],
            )
            rows = [r[0] for r in cursor.fetchall()]
            assert rows == ["referral_partner", "revenue_share_rule"]

    def test_no_tenant_id_or_current_flag_columns(self, tenant_a: Tenant) -> None:
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
                WHERE table_schema = %s
                  AND table_name = 'revenue_share_rule'
                """,
                [tenant_a.schema_name],
            )
            cols = {row[0]: row[1:] for row in cursor.fetchall()}

        assert "tenant_id" not in cols
        assert "tenant" not in cols
        assert "is_current" not in cols
        assert "is_active" not in cols
        assert set(cols.keys()) == {
            "id",
            "referral_partner_id",
            "test_category",
            "branch_id",
            "percent",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        }
        # Verify numeric(5,2)
        assert cols["percent"] == ("numeric", 5, 2, "NO")
        assert cols["referral_partner_id"][3] == "NO"
        assert cols["test_category"][3] == "YES"
        assert cols["branch_id"][3] == "YES"
        assert cols["effective_from"][3] == "NO"
        assert cols["effective_to"][3] == "YES"

    def test_percent_check_constraint_bounds_0_and_100_succeed(
        self, tenant_a: Tenant
    ) -> None:
        with schema_context(tenant_a.schema_name):
            rule_zero = RevenueShareRuleFactory(
                percent=Decimal("0.00"),
                test_category=None,
                branch=None,
            )
            rule_hundred = RevenueShareRuleFactory(
                percent=Decimal("100.00"),
            )
            rule_zero.refresh_from_db()
            rule_hundred.refresh_from_db()
            assert isinstance(rule_zero.percent, Decimal)
            assert rule_zero.percent == Decimal("0.00")
            assert rule_hundred.percent == Decimal("100.00")

    @pytest.mark.parametrize(
        "invalid_percent",
        [
            Decimal("-0.01"),
            Decimal("-1.00"),
            Decimal("100.01"),
            Decimal("101.00"),
        ],
    )
    def test_percent_check_constraint_rejects_out_of_range_orm(
        self, tenant_a: Tenant, invalid_percent: Decimal
    ) -> None:
        with schema_context(tenant_a.schema_name):
            partner = ReferralPartnerFactory()
            with pytest.raises(IntegrityError):
                RevenueShareRule.objects.create(
                    referral_partner=partner,
                    percent=invalid_percent,
                    effective_from=date(2026, 1, 1),
                )

    @pytest.mark.parametrize("raw_percent", ["-1.00", "101.00"])
    def test_percent_check_constraint_rejects_direct_sql(
        self, tenant_a: Tenant, raw_percent: str
    ) -> None:
        with schema_context(tenant_a.schema_name):
            partner = ReferralPartnerFactory()
            with pytest.raises(IntegrityError), connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO revenue_share_rule (
                        id, referral_partner_id, test_category, branch_id,
                        percent, effective_from, effective_to, created_at, updated_at
                    )
                    VALUES (
                        gen_random_uuid(), %s, NULL, NULL,
                        %s::numeric(5,2), '2026-01-01', NULL, now(), now()
                    )
                    """,
                    [str(partner.id), raw_percent],
                )

    def test_foreign_keys_protect_against_deletion(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            partner = ReferralPartnerFactory()
            branch = BranchFactory()
            RevenueShareRuleFactory(referral_partner=partner, branch=branch)

            with pytest.raises(models.ProtectedError):
                partner.delete()

            with pytest.raises(models.ProtectedError):
                branch.delete()

    def test_fk_indexes_exist_in_pg_indexes(self, tenant_a: Tenant) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s
                  AND tablename = 'revenue_share_rule'
                """,
                [tenant_a.schema_name],
            )
            index_names = {row[0] for row in cursor.fetchall()}

        assert "idx_revenue_share_rule_referral_partner_id" in index_names
        assert "idx_revenue_share_rule_branch_id" in index_names
