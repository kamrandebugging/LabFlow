from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest
from django.apps import apps
from django.db import DatabaseError, connection, transaction
from django_tenants.utils import schema_context, tenant_context

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
from tests.factories.automation import WebhookDeliveryFactory
from tests.factories.notifications import (
    NotificationFactory,
    NotificationTemplateFactory,
)
from tests.factories.partners import (
    ReferralPartnerFactory,
    RevenueShareRuleFactory,
    SettlementFactory,
    SettlementLineFactory,
    ShareLedgerEntryFactory,
)
from tests.isolation.generator import (
    EXCLUDED_MODELS,
    get_tenant_models,
    is_model_excluded,
    validate_tenant_model_factory,
)

revoke_migration_module = import_module(
    "apps.partners.migrations.0005_share_ledger_entry_append_only"
)

LAB8_MODELS: list[type[Any]] = [
    ReferralPartner,
    RevenueShareRule,
    ShareLedgerEntry,
    Settlement,
    SettlementLine,
    NotificationTemplate,
    Notification,
    WebhookDelivery,
]

LAB8_MUTABLE_TABLES = (
    "referral_partner",
    "revenue_share_rule",
    "settlement",
    "settlement_line",
    "notification_template",
    "notification",
    "webhook_delivery",
)


def _table_privileges(schema_name: str, table_name: str) -> set[str]:
    """Return explicit role_table_grants for current_user on
    (schema_name, table_name).
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT privilege_type
            FROM information_schema.role_table_grants
            WHERE table_schema = %s
              AND table_name = %s
              AND grantee = current_user;
            """,
            [schema_name, table_name],
        )
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.django_db
class TestSubtask6RevokeAndGenerator:
    """Verifies KAN-70 / Epic LAB-8 Subtask 6:

    - REVOKE UPDATE, DELETE, TRUNCATE on share_ledger_entry in tenant schemas.
    - SELECT and INSERT remain granted.
    - No exceptions: no update/delete bypass.
    - Nothing beyond share_ledger_entry revoked in this batch.
    - Migration is reversible.
    - Factory rule (KAN-31) discharged for all 8 LAB-8 models.
    - Generator coverage (KAN-32) confirms all 8 models covered with zero exclusions.
    """

    def test_append_only_privileges_revoked_on_share_ledger_entry(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            grants = _table_privileges(tenant_a.schema_name, "share_ledger_entry")
            assert "SELECT" in grants, "SELECT missing on share_ledger_entry"
            assert "INSERT" in grants, "INSERT missing on share_ledger_entry"
            assert "UPDATE" not in grants, "UPDATE still granted on share_ledger_entry"
            assert "DELETE" not in grants, "DELETE still granted on share_ledger_entry"
            assert "TRUNCATE" not in grants, (
                "TRUNCATE still granted on share_ledger_entry"
            )

    def test_nothing_revoked_beyond_share_ledger_entry(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            for table_name in LAB8_MUTABLE_TABLES:
                grants = _table_privileges(tenant_a.schema_name, table_name)
                assert "SELECT" in grants, f"SELECT missing on {table_name}"
                assert "INSERT" in grants, f"INSERT missing on {table_name}"
                assert "UPDATE" in grants, (
                    f"Mutable table {table_name} unexpectedly lost UPDATE privilege"
                )
                assert "DELETE" in grants, (
                    f"Mutable table {table_name} unexpectedly lost DELETE privilege"
                )

    def test_revoke_migration_is_reversible(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            with connection.schema_editor() as editor:
                revoke_migration_module.reverse_append_only_revoke(apps, editor)

            grants = _table_privileges(tenant_a.schema_name, "share_ledger_entry")
            assert {
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "TRUNCATE",
            }.issubset(grants)

            with connection.schema_editor() as editor:
                revoke_migration_module.apply_append_only_revoke(apps, editor)

            grants_after = _table_privileges(tenant_a.schema_name, "share_ledger_entry")
            assert "SELECT" in grants_after
            assert "INSERT" in grants_after
            assert "UPDATE" not in grants_after
            assert "DELETE" not in grants_after
            assert "TRUNCATE" not in grants_after

    def test_share_ledger_entry_no_exceptions_update_delete_denied_under_app_role(
        self, tenant_a: Tenant
    ) -> None:
        """Confirms that under an unprivileged application DB probe role,

        UPDATE and DELETE on share_ledger_entry are denied by PostgreSQL
        permission check.
        """
        with tenant_context(tenant_a):
            entry = ShareLedgerEntryFactory()

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_roles
                            WHERE rolname = 'labflow_subtask6_probe'
                        ) THEN
                            CREATE ROLE labflow_subtask6_probe
                                NOLOGIN NOSUPERUSER NOBYPASSRLS;
                        END IF;
                    END
                    $$;
                    """
                )
                q_schema = connection.ops.quote_name(tenant_a.schema_name)
                cursor.execute(
                    f"GRANT USAGE ON SCHEMA {q_schema} TO labflow_subtask6_probe;"
                )
                cursor.execute(
                    f'REVOKE ALL ON TABLE {q_schema}."share_ledger_entry" '
                    f"FROM labflow_subtask6_probe;"
                )
                cursor.execute(
                    f'GRANT SELECT, INSERT ON TABLE {q_schema}."share_ledger_entry" '
                    f"TO labflow_subtask6_probe;"
                )

                # SELECT succeeds under probe role
                with transaction.atomic():
                    cursor.execute("SET LOCAL ROLE labflow_subtask6_probe;")
                    cursor.execute(
                        f'SELECT id FROM {q_schema}."share_ledger_entry" '
                        f"WHERE id = %s;",
                        [str(entry.id)],
                    )
                    assert cursor.fetchone() is not None

                # UPDATE fails
                with (
                    pytest.raises(DatabaseError) as exc_update,
                    transaction.atomic(),
                ):
                    cursor.execute("SET LOCAL ROLE labflow_subtask6_probe;")
                    cursor.execute(
                        f"""
                        UPDATE {q_schema}."share_ledger_entry"
                        SET amount = 999.00
                        WHERE id = %s;
                        """,
                        [str(entry.id)],
                    )
                assert (
                    "permission denied" in str(exc_update.value).lower()
                    or "must be owner" in str(exc_update.value).lower()
                )

                # DELETE fails
                with (
                    pytest.raises(DatabaseError) as exc_delete,
                    transaction.atomic(),
                ):
                    cursor.execute("SET LOCAL ROLE labflow_subtask6_probe;")
                    cursor.execute(
                        f"""
                        DELETE FROM {q_schema}."share_ledger_entry"
                        WHERE id = %s;
                        """,
                        [str(entry.id)],
                    )
                assert (
                    "permission denied" in str(exc_delete.value).lower()
                    or "must be owner" in str(exc_delete.value).lower()
                )

    def test_factory_rule_discharged_for_all_8_lab8_models(
        self, tenant_a: Tenant
    ) -> None:
        """KAN-31: All 8 LAB-8 models have working factories that execute cleanly

        inside tenant schema context.
        """
        with schema_context(tenant_a.schema_name):
            p = ReferralPartnerFactory()
            assert ReferralPartner.objects.filter(id=p.id).exists()

            r = RevenueShareRuleFactory()
            assert RevenueShareRule.objects.filter(id=r.id).exists()

            e = ShareLedgerEntryFactory()
            assert ShareLedgerEntry.objects.filter(id=e.id).exists()

            s = SettlementFactory()
            assert Settlement.objects.filter(id=s.id).exists()

            sl = SettlementLineFactory()
            assert SettlementLine.objects.filter(id=sl.id).exists()

            nt = NotificationTemplateFactory()
            assert NotificationTemplate.objects.filter(id=nt.id).exists()

            n = NotificationFactory()
            assert Notification.objects.filter(id=n.id).exists()

            w = WebhookDeliveryFactory()
            assert WebhookDelivery.objects.filter(id=w.id).exists()

    def test_generator_coverage_includes_all_8_lab8_models_with_zero_exclusions(
        self,
    ) -> None:
        """KAN-32: All 8 LAB-8 models are discoverable by the generator,

        none are excluded, and each resolves its <Model>Factory without error.
        """
        registered_tenant_models = get_tenant_models()

        for model_cls in LAB8_MODELS:
            assert model_cls in registered_tenant_models, (
                f"{model_cls.__name__} not found in get_tenant_models()"
            )

            # None of the LAB-8 models may be excluded
            excluded, reason = is_model_excluded(model_cls)
            assert not excluded, (
                f"{model_cls.__name__} must NOT be excluded from "
                f"isolation coverage: {reason}"
            )
            model_key = f"{model_cls._meta.app_label}.{model_cls.__name__}"
            assert model_key not in EXCLUDED_MODELS

            # Must resolve factory cleanly
            factory_cls = validate_tenant_model_factory(model_cls)
            assert factory_cls is not None
            assert factory_cls.__name__ == f"{model_cls.__name__}Factory"

    def test_migration_not_applied_to_public_schema(self) -> None:
        """Verifies that 0005_share_ledger_entry_append_only never runs
        in public schema.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app, name
                FROM public.django_migrations
                WHERE app = 'partners' AND name = '0005_share_ledger_entry_append_only';
                """
            )
            rows = cursor.fetchall()
            assert len(rows) == 0, f"Tenant migration found in public schema: {rows}"
