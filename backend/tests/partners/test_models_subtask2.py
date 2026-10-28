from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, models, transaction
from django_tenants.utils import schema_context

from apps.core.models import Tenant
from apps.partners.models import ShareLedgerEntry
from tests.factories.billing import PaymentFactory
from tests.factories.partners import (
    ReferralPartnerFactory,
    ShareLedgerEntryFactory,
)


@pytest.mark.django_db
class TestShareLedgerEntryModel:
    """
    Verifies KAN-66 (Doc 02 §5.8, §7, §8, §12, §20 OQ-22; Doc 05 §6):
    - share_ledger_entry exists in tenant schemas only, never public.
    - Exact column set: id, payment_id, referral_partner_id, rule_id, amount,
      percent_applied, basis_amount, period, created_at.
    - Structural immutability: NO status column, NO settlement_id column,
      NO updated_at column, NO deleted_at column, NO tenant_id column.
    - UNIQUE(payment_id) (uq_share_ledger_entry_payment_id) enforced via ORM
      and raw SQL.
    - Positive accrual and negative compensating reversal amounts allowed.
    - CHECK constraints on percent_applied (0..100) and period (YYYY-MM).
    - FK PROTECT on payment_id, referral_partner_id, and rule_id.
    - All FK indexes present in pg_indexes.
    """

    def test_table_exists_in_tenant_schema_and_not_public(
        self, tenant_a: Tenant
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'share_ledger_entry'
                """
            )
            assert cursor.fetchall() == []

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = 'share_ledger_entry'
                """,
                [tenant_a.schema_name],
            )
            assert [r[0] for r in cursor.fetchall()] == ["share_ledger_entry"]

    def test_exact_columns_and_immutability_shape(self, tenant_a: Tenant) -> None:
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
                  AND table_name = 'share_ledger_entry'
                """,
                [tenant_a.schema_name],
            )
            cols = {row[0]: row[1:] for row in cursor.fetchall()}

        # Forbidden columns per KAN-66 & OQ-22
        for forbidden in (
            "status",
            "settlement_id",
            "settlement",
            "updated_at",
            "deleted_at",
            "tenant_id",
            "tenant",
        ):
            assert forbidden not in cols

        assert set(cols.keys()) == {
            "id",
            "payment_id",
            "referral_partner_id",
            "rule_id",
            "amount",
            "percent_applied",
            "basis_amount",
            "period",
            "created_at",
        }
        assert cols["amount"] == ("numeric", 12, 2, "NO")
        assert cols["percent_applied"] == ("numeric", 5, 2, "NO")
        assert cols["basis_amount"] == ("numeric", 12, 2, "NO")
        assert cols["payment_id"][3] == "NO"
        assert cols["referral_partner_id"][3] == "NO"
        assert cols["rule_id"][3] == "YES"
        assert cols["period"][3] == "NO"
        assert cols["created_at"][3] == "NO"

    def test_unique_payment_id_enforced_orm_and_raw_sql(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            entry = ShareLedgerEntryFactory()

            # Second entry for the same payment via ORM must fail
            with pytest.raises(IntegrityError), transaction.atomic():
                ShareLedgerEntry.objects.create(
                    payment=entry.payment,
                    referral_partner=entry.referral_partner,
                    rule=entry.rule,
                    amount=Decimal("100.00"),
                    percent_applied=Decimal("10.00"),
                    basis_amount=Decimal("1000.00"),
                    period="2026-10",
                )

            # Second entry for the same payment via direct SQL must also fail
            with (
                pytest.raises(IntegrityError),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    """
                    INSERT INTO share_ledger_entry (
                        id, payment_id, referral_partner_id, rule_id,
                        amount, percent_applied, basis_amount, period, created_at
                    )
                    VALUES (
                        gen_random_uuid(), %s, %s, NULL,
                        100.00, 10.00, 1000.00, '2026-10', now()
                    )
                    """,
                    [str(entry.payment_id), str(entry.referral_partner_id)],
                )

    def test_positive_accrual_and_negative_reversal_amounts_allowed(
        self, tenant_a: Tenant
    ) -> None:
        with schema_context(tenant_a.schema_name):
            accrual = ShareLedgerEntryFactory(
                amount=Decimal("800.00"),
                percent_applied=Decimal("20.00"),
                basis_amount=Decimal("4000.00"),
                period="2026-09",
            )
            reversal = ShareLedgerEntryFactory(
                amount=Decimal("-800.00"),
                percent_applied=Decimal("20.00"),
                basis_amount=Decimal("4000.00"),
                rule=None,
                period="2026-10",
            )
            accrual.refresh_from_db()
            reversal.refresh_from_db()
            assert accrual.amount == Decimal("800.00")
            assert reversal.amount == Decimal("-800.00")
            assert reversal.rule is None

    @pytest.mark.parametrize(
        "bad_percent",
        [Decimal("-0.01"), Decimal("-1.00"), Decimal("100.01"), Decimal("101.00")],
    )
    def test_percent_applied_check_constraint(
        self, tenant_a: Tenant, bad_percent: Decimal
    ) -> None:
        with schema_context(tenant_a.schema_name):
            payment = PaymentFactory()
            partner = ReferralPartnerFactory()
            with pytest.raises(IntegrityError):
                ShareLedgerEntry.objects.create(
                    payment=payment,
                    referral_partner=partner,
                    rule=None,
                    amount=Decimal("10.00"),
                    percent_applied=bad_percent,
                    basis_amount=Decimal("100.00"),
                    period="2026-10",
                )

    @pytest.mark.parametrize(
        "bad_period",
        ["2026-1", "26-10", "2026/10", "202610", "oct-2026", ""],
    )
    def test_period_format_check_constraint(
        self, tenant_a: Tenant, bad_period: str
    ) -> None:
        with schema_context(tenant_a.schema_name):
            payment = PaymentFactory()
            partner = ReferralPartnerFactory()
            with pytest.raises(IntegrityError):
                ShareLedgerEntry.objects.create(
                    payment=payment,
                    referral_partner=partner,
                    rule=None,
                    amount=Decimal("10.00"),
                    percent_applied=Decimal("10.00"),
                    basis_amount=Decimal("100.00"),
                    period=bad_period,
                )

    def test_foreign_keys_protect_against_deletion(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            entry = ShareLedgerEntryFactory()
            payment = entry.payment
            partner = entry.referral_partner
            assert entry.rule is not None
            rule = entry.rule

            with pytest.raises(models.ProtectedError):
                payment.delete()

            with pytest.raises(models.ProtectedError):
                partner.delete()

            with pytest.raises(models.ProtectedError):
                rule.delete()

    def test_indexes_exist_in_pg_indexes(self, tenant_a: Tenant) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s
                  AND tablename = 'share_ledger_entry'
                """,
                [tenant_a.schema_name],
            )
            index_names = {row[0] for row in cursor.fetchall()}

        assert "uq_share_ledger_entry_payment_id" in index_names
        assert "idx_share_ledger_entry_payment_id" in index_names
        assert "idx_share_ledger_entry_referral_partner_id" in index_names
        assert "idx_share_ledger_entry_rule_id" in index_names
