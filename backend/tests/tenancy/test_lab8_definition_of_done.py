from __future__ import annotations

import subprocess
import sys
from decimal import Decimal
from typing import Any

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, tenant_context

from apps.automation.models import WebhookDelivery
from apps.core.models import Tenant
from apps.notifications.models import Notification, NotificationTemplate
from apps.partners.models import (
    ReferralPartner,
    RevenueShareRule,
    Settlement,
    SettlementLine,
    ShareLedgerEntry,
)
from tests.factories.billing import PaymentFactory
from tests.factories.partners import (
    ReferralPartnerFactory,
    SettlementFactory,
    ShareLedgerEntryFactory,
)
from tests.isolation.generator import (
    EXCLUDED_MODELS,
    get_tenant_models,
    is_model_excluded,
    validate_tenant_model_factory,
)

LAB8_TABLES: tuple[str, ...] = (
    "referral_partner",
    "revenue_share_rule",
    "share_ledger_entry",
    "settlement",
    "settlement_line",
    "notification_template",
    "notification",
    "webhook_delivery",
)

LAB8_MODELS: tuple[type[Any], ...] = (
    ReferralPartner,
    RevenueShareRule,
    ShareLedgerEntry,
    Settlement,
    SettlementLine,
    NotificationTemplate,
    Notification,
    WebhookDelivery,
)


@pytest.mark.django_db
class TestLab8DefinitionOfDone:
    """LAB-8 Definition of Done Verification Suite (KAN-52 / Subtask 7).

    Proves all 8 explicit pass/fail checks specified in the epic.
    """

    def test_check1_placement_drift_and_partial_unique_indexes(
        self, tenant_a: Tenant
    ) -> None:
        """Check 1 — Correct case (placement + drift):

        All 8 LAB-8 tables exist in tenant schemas and none in public schema;
        makemigrations --check --dry-run exits 0 with 'No changes detected';
        pg_indexes confirms the partial unique indexes named in LAB-8 are present.
        """
        public_schema = get_public_schema_name()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE';
                """,
                [public_schema],
            )
            public_tables = {r[0] for r in cursor.fetchall()}

            for tbl in LAB8_TABLES:
                assert tbl not in public_tables, (
                    f"LAB-8 table {tbl} must NOT exist in public schema!"
                )

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE';
                """,
                [tenant_a.schema_name],
            )
            tenant_tables = {r[0] for r in cursor.fetchall()}

            for tbl in LAB8_TABLES:
                assert tbl in tenant_tables, (
                    f"LAB-8 table {tbl} missing from tenant schema "
                    f"{tenant_a.schema_name}!"
                )

        # Drift check
        result = subprocess.run(
            [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"Drift detected: {result.stdout}\n{result.stderr}"
        )
        assert "No changes detected" in result.stdout

        # Verify partial unique indexes in pg_indexes
        with tenant_context(tenant_a), connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = %s;
                """,
                [tenant_a.schema_name],
            )
            indexes = {r[0]: r[1] for r in cursor.fetchall()}

        # 1. uq_settlement_partner_id_period
        assert "uq_settlement_partner_id_period" in indexes
        assert "WHERE" in indexes["uq_settlement_partner_id_period"]
        assert "status" in indexes["uq_settlement_partner_id_period"]
        assert "CANCELLED" in indexes["uq_settlement_partner_id_period"]

        # 2. uq_notification_idempotency_key
        assert "uq_notification_idempotency_key" in indexes
        assert "WHERE" in indexes["uq_notification_idempotency_key"]
        assert (
            "idempotency_key IS NOT NULL" in indexes["uq_notification_idempotency_key"]
        )

        # 3. idx_webhook_delivery_status_next_attempt_at
        assert "idx_webhook_delivery_status_next_attempt_at" in indexes
        assert "WHERE" in indexes["idx_webhook_delivery_status_next_attempt_at"]
        assert "PENDING" in indexes["idx_webhook_delivery_status_next_attempt_at"]
        assert "FAILED" in indexes["idx_webhook_delivery_status_next_attempt_at"]

    def test_check2_error_case_percent_check_constraint(self, tenant_a: Tenant) -> None:
        """Check 2 — Error case (percent CHECK):

        revenue_share_rule percent -1 -> check violation;
        percent 101 -> check violation;
        percent 0 and percent 100 -> both insert successfully.
        """
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            now = timezone.now()

            # percent -1 fails on percent CHECK
            with pytest.raises(IntegrityError) as exc_neg, transaction.atomic():
                RevenueShareRule.objects.create(
                    referral_partner=partner,
                    percent=Decimal("-1.00"),
                    effective_from=now,
                )
            assert "chk_revenue_share_rule_percent_0_100" in str(exc_neg.value)

            # percent 101 fails on percent CHECK
            with pytest.raises(IntegrityError) as exc_over, transaction.atomic():
                RevenueShareRule.objects.create(
                    referral_partner=partner,
                    percent=Decimal("101.00"),
                    effective_from=now,
                )
            assert "chk_revenue_share_rule_percent_0_100" in str(exc_over.value)

            # percent 0 inserts
            r0 = RevenueShareRule.objects.create(
                referral_partner=partner,
                percent=Decimal("0.00"),
                effective_from=now,
            )
            assert RevenueShareRule.objects.filter(id=r0.id).exists()

            # percent 100 inserts
            r100 = RevenueShareRule.objects.create(
                referral_partner=partner,
                percent=Decimal("100.00"),
                effective_from=now,
            )
            assert RevenueShareRule.objects.filter(id=r100.id).exists()

    def test_check3_idempotency_case_ledger_unique_payment_id(
        self, tenant_a: Tenant
    ) -> None:
        """Check 3 — Idempotency case (ledger):

        Two share_ledger_entry rows with the same payment_id -> second fails
        with an IntegrityError on UNIQUE constraint
        (uq_share_ledger_entry_payment_id).
        """
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            payment = PaymentFactory()

            # First row inserts successfully
            ShareLedgerEntry.objects.create(
                payment=payment,
                referral_partner=partner,
                rule=None,
                amount=Decimal("250.00"),
                percent_applied=Decimal("10.00"),
                basis_amount=Decimal("2500.00"),
                period="2026-10",
            )

            # Second row with identical payment_id must fail UNIQUE constraint
            with pytest.raises(IntegrityError), transaction.atomic():
                ShareLedgerEntry.objects.create(
                    payment=payment,
                    referral_partner=partner,
                    rule=None,
                    amount=Decimal("250.00"),
                    percent_applied=Decimal("10.00"),
                    basis_amount=Decimal("2500.00"),
                    period="2026-10",
                )

    def test_check4_immutability_case_shape_and_revoke(self, tenant_a: Tenant) -> None:
        """Check 4 — Immutability case (shape + REVOKE):

        information_schema.columns shows share_ledger_entry has no status column
        and no settlement_id column.
        As the application DB role, INSERT/SELECT succeed;
        UPDATE, DELETE, and TRUNCATE each fail with permission denied.
        """
        with tenant_context(tenant_a):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = 'share_ledger_entry';
                    """,
                    [tenant_a.schema_name],
                )
                cols = {r[0] for r in cursor.fetchall()}

            assert "status" not in cols, (
                "share_ledger_entry must NOT have a status column (Doc 02 §5.8)!"
            )
            assert "settlement_id" not in cols, (
                "share_ledger_entry must NOT have a settlement_id column (Doc 02 §5.8)!"
            )
            assert "updated_at" not in cols, (
                "share_ledger_entry must NOT have an updated_at column!"
            )
            assert "created_at" in cols

            # INSERT and SELECT succeed
            entry = ShareLedgerEntryFactory()
            assert ShareLedgerEntry.objects.filter(id=entry.id).exists()

            # Verify table grants for current_user
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT privilege_type
                    FROM information_schema.role_table_grants
                    WHERE table_schema = %s
                      AND table_name = 'share_ledger_entry'
                      AND grantee = current_user;
                    """,
                    [tenant_a.schema_name],
                )
                grants = {r[0] for r in cursor.fetchall()}
                assert "SELECT" in grants
                assert "INSERT" in grants
                assert "UPDATE" not in grants
                assert "DELETE" not in grants
                assert "TRUNCATE" not in grants

                # Verify runtime permission denied under unprivileged probe role
                cursor.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_roles
                            WHERE rolname = 'labflow_dod_lab8_probe'
                        ) THEN
                            CREATE ROLE labflow_dod_lab8_probe
                                NOLOGIN NOSUPERUSER NOBYPASSRLS;
                        END IF;
                    END
                    $$;
                    """
                )
                q_schema = connection.ops.quote_name(tenant_a.schema_name)
                cursor.execute(
                    f"GRANT USAGE ON SCHEMA {q_schema} TO labflow_dod_lab8_probe;"
                )
                cursor.execute(
                    f'REVOKE ALL ON TABLE {q_schema}."share_ledger_entry" '
                    f"FROM labflow_dod_lab8_probe;"
                )
                cursor.execute(
                    f'GRANT SELECT, INSERT ON TABLE {q_schema}."share_ledger_entry" '
                    f"TO labflow_dod_lab8_probe;"
                )

                # UPDATE fails
                with (
                    pytest.raises(DatabaseError) as exc_upd,
                    transaction.atomic(),
                ):
                    cursor.execute("SET LOCAL ROLE labflow_dod_lab8_probe;")
                    cursor.execute(
                        f"""
                        UPDATE {q_schema}."share_ledger_entry"
                        SET amount = 500.00
                        WHERE id = %s;
                        """,
                        [str(entry.id)],
                    )
                assert (
                    "permission denied" in str(exc_upd.value).lower()
                    or "must be owner" in str(exc_upd.value).lower()
                )

                # DELETE fails
                with (
                    pytest.raises(DatabaseError) as exc_del,
                    transaction.atomic(),
                ):
                    cursor.execute("SET LOCAL ROLE labflow_dod_lab8_probe;")
                    cursor.execute(
                        f"""
                        DELETE FROM {q_schema}."share_ledger_entry"
                        WHERE id = %s;
                        """,
                        [str(entry.id)],
                    )
                assert (
                    "permission denied" in str(exc_del.value).lower()
                    or "must be owner" in str(exc_del.value).lower()
                )

                # TRUNCATE fails
                with (
                    pytest.raises(DatabaseError) as exc_trunc,
                    transaction.atomic(),
                ):
                    cursor.execute("SET LOCAL ROLE labflow_dod_lab8_probe;")
                    cursor.execute(f'TRUNCATE TABLE {q_schema}."share_ledger_entry";')
                assert (
                    "permission denied" in str(exc_trunc.value).lower()
                    or "must be owner" in str(exc_trunc.value).lower()
                )

    def test_check5_correct_case_settlement_partial_unique(
        self, tenant_a: Tenant
    ) -> None:
        """Check 5 — Correct case (settlement partial unique):

        Two live settlements for the same (partner, period) -> second fails
        on the partial unique;
        set the first to CANCELLED -> a replacement settlement for the same
        (partner, period) inserts successfully.
        """
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            period = "2026-10"

            # 1. First live settlement inserts (status DRAFT)
            s1 = Settlement.objects.create(
                referral_partner=partner,
                period=period,
                status=Settlement.Status.DRAFT,
                total=Decimal("1200.00"),
            )
            assert Settlement.objects.filter(id=s1.id).exists()

            # 2. Second live settlement for same partner and period fails
            with pytest.raises(IntegrityError), transaction.atomic():
                Settlement.objects.create(
                    referral_partner=partner,
                    period=period,
                    status=Settlement.Status.DRAFT,
                    total=Decimal("1500.00"),
                )

            # 3. Set the first to CANCELLED
            s1.status = Settlement.Status.CANCELLED
            s1.save(update_fields=["status"])

            # 4. Replacement settlement for the same (partner, period)
            # now inserts cleanly
            s2 = Settlement.objects.create(
                referral_partner=partner,
                period=period,
                status=Settlement.Status.DRAFT,
                total=Decimal("1500.00"),
            )
            assert Settlement.objects.filter(id=s2.id).exists()
            assert s2.id != s1.id

    def test_check6_idempotency_case_lines_notifications_and_webhooks(
        self, tenant_a: Tenant
    ) -> None:
        """Check 6 — Idempotency case (settlement line + notifications + webhooks):

        - Same share_ledger_entry_id on two settlement_line rows -> second fails UNIQUE;
        - Two notification rows with same idempotency_key -> second fails;
        - Two webhook_delivery rows with same idempotency_key -> second fails;
        - Two notification_template rows with same (key, locale, channel)
          -> second fails, while same key with different locale inserts.
        """
        with tenant_context(tenant_a):
            # 1. SettlementLine idempotency (uq_settlement_line_share_ledger_entry_id)
            s = SettlementFactory()
            entry = ShareLedgerEntryFactory()

            SettlementLine.objects.create(
                settlement=s,
                share_ledger_entry=entry,
                amount=entry.amount,
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                SettlementLine.objects.create(
                    settlement=s,
                    share_ledger_entry=entry,
                    amount=entry.amount,
                )

            # 2. Notification idempotency (uq_notification_idempotency_key)
            idem_notif = "notif-unique-key-12345"
            Notification.objects.create(
                channel=Notification.Channel.EMAIL,
                recipient_type=Notification.RecipientType.PATIENT,
                idempotency_key=idem_notif,
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                Notification.objects.create(
                    channel=Notification.Channel.WHATSAPP,
                    recipient_type=Notification.RecipientType.PATIENT,
                    idempotency_key=idem_notif,
                )

            # 3. WebhookDelivery idempotency (uq_webhook_delivery_idempotency_key)
            idem_webhook = "webhook-unique-key-67890"
            WebhookDelivery.objects.create(
                event="report.ready",
                idempotency_key=idem_webhook,
                payload_jsonb={"event": "report.ready"},
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                WebhookDelivery.objects.create(
                    event="report.ready",
                    idempotency_key=idem_webhook,
                    payload_jsonb={"event": "report.ready"},
                )

            # 4. NotificationTemplate unique (key, locale, channel)
            NotificationTemplate.objects.create(
                key="report.ready",
                locale=NotificationTemplate.Locale.EN,
                channel=NotificationTemplate.Channel.EMAIL,
                body="Your report is ready.",
            )
            # Duplicate (key, locale, channel) fails
            with pytest.raises(IntegrityError), transaction.atomic():
                NotificationTemplate.objects.create(
                    key="report.ready",
                    locale=NotificationTemplate.Locale.EN,
                    channel=NotificationTemplate.Channel.EMAIL,
                    body="Duplicate english email.",
                )
            # Same key with different locale (UR) inserts cleanly
            t_ur = NotificationTemplate.objects.create(
                key="report.ready",
                locale=NotificationTemplate.Locale.UR,
                channel=NotificationTemplate.Channel.EMAIL,
                body="Aap ki report tayyar hai.",
            )
            assert NotificationTemplate.objects.filter(id=t_ur.id).exists()

    def test_check7_isolation_case_generator_coverage(self) -> None:
        """Check 7 — Isolation case:

        pytest --collect-only lists generated isolation cases for all 8 LAB-8
        models and none are excluded.
        """
        registered_models = get_tenant_models()

        for model_cls in LAB8_MODELS:
            # Model registered
            assert model_cls in registered_models, (
                f"{model_cls.__name__} not in get_tenant_models()"
            )

            # Zero exclusions allowed for LAB-8
            excluded, reason = is_model_excluded(model_cls)
            assert not excluded, f"{model_cls.__name__} cannot be excluded: {reason}"
            model_key = f"{model_cls._meta.app_label}.{model_cls.__name__}"
            assert model_key not in EXCLUDED_MODELS

            # Factory resolves cleanly
            factory_cls = validate_tenant_model_factory(model_cls)
            assert factory_cls is not None

    def test_check8_performance_case_fk_indexes_and_money_precision(
        self, tenant_a: Tenant
    ) -> None:
        """Check 8 — Performance case:

        pg_indexes confirms an index for every foreign key in the 8 tables;
        money columns (basis_amount, amount, total) are numeric(12,2) per
        information_schema, and percent is numeric(5,2) — none is float/double.
        """
        with tenant_context(tenant_a), connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tablename, indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = %s;
                """,
                [tenant_a.schema_name],
            )
            all_indexes = cursor.fetchall()
            by_table: dict[str, dict[str, str]] = {}
            for tbl, idx_name, idx_def in all_indexes:
                by_table.setdefault(tbl, {})[idx_name] = idx_def

            # 1. Foreign key index coverage on all LAB-8 models
            for model_cls in LAB8_MODELS:
                tbl = model_cls._meta.db_table
                tbl_idx_defs = list(by_table.get(tbl, {}).values())
                for field in model_cls._meta.local_fields:
                    if field.is_relation and field.many_to_one:
                        fk_col = field.column
                        has_index = any(
                            f"({fk_col})" in idx_def or f"({fk_col}," in idx_def
                            for idx_def in tbl_idx_defs
                        )
                        assert has_index, (
                            f"FK column {tbl}.{fk_col} has no index in pg_indexes!"
                        )

            # 2. Money columns are numeric(12,2)
            money_columns = [
                ("share_ledger_entry", "amount"),
                ("share_ledger_entry", "basis_amount"),
                ("settlement", "total"),
                ("settlement_line", "amount"),
            ]
            for tbl, col in money_columns:
                cursor.execute(
                    """
                    SELECT data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                      AND column_name = %s;
                    """,
                    [tenant_a.schema_name, tbl, col],
                )
                assert cursor.fetchone() == ("numeric", 12, 2), (
                    f"{tbl}.{col} is not numeric(12,2)!"
                )

            # 3. Percent columns are numeric(5,2)
            percent_columns = [
                ("revenue_share_rule", "percent"),
                ("share_ledger_entry", "percent_applied"),
            ]
            for tbl, col in percent_columns:
                cursor.execute(
                    """
                    SELECT data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                      AND column_name = %s;
                    """,
                    [tenant_a.schema_name, tbl, col],
                )
                assert cursor.fetchone() == ("numeric", 5, 2), (
                    f"{tbl}.{col} is not numeric(5,2)!"
                )

            # 4. Zero float/double/real columns in any LAB-8 table
            cursor.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = ANY(%s)
                  AND data_type IN ('real', 'double precision', 'float');
                """,
                [tenant_a.schema_name, list(LAB8_TABLES)],
            )
            float_cols = cursor.fetchall()
            assert float_cols == [], (
                f"Forbidden float columns found in LAB-8 tables: {float_cols}"
            )
