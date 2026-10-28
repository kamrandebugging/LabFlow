from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.db import DatabaseError, connection
from django_tenants.utils import schema_context

from apps.audit.models import AuditLog
from apps.billing.models import Payment
from apps.core.models import Tenant
from apps.partners.models import ShareLedgerEntry
from apps.platform.provisioning import (
    STEP_HANDLERS,
    TENANT_APPEND_ONLY_TABLES,
    ProvisioningStateSnapshot,
    ProvisionTenantInput,
    create_tenant_provisioning,
    execute_step_p3_create_schema,
    execute_step_p4_migrate_schema,
    execute_step_p5_revoke_append_only,
    get_provisioning_state,
)
from apps.platform.tasks import provision_tenant_task
from apps.reports.models import ReportVersion
from apps.results.models import CriticalNotification
from apps.samples.models import SampleEvent
from tests.factories import (
    AuditLogFactory,
    CriticalNotificationFactory,
    PaymentFactory,
    PlanFactory,
    PlatformUserFactory,
    ReportVersionFactory,
    SampleEventFactory,
    ShareLedgerEntryFactory,
)


def _drop_schema_if_exists(schema_name: str) -> None:
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


@pytest.mark.django_db(transaction=True)
class TestStepP5AppendOnlyRevokeEnforcement:
    """
    Subtask 4 (KAN-75): Step P-5 — apply and confirm the REVOKE set and append-only
    protections on all 6 tenant append-only tables in a freshly provisioned
    schema (TN-07).
    """

    def test_tn07_provisioned_schema_blocks_update_delete_and_truncate_on_all_6_tables(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "revokelab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Revoke Test Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@revokelab.pk",
                        owner_name="Dr. Revoke",
                        actor_id=sa.id,
                    )
                )

            task_result = provision_tenant_task(slug)
            assert task_result["status"] == "active"
            assert "P-5" in task_result["completed_steps"]

            # Re-running P-5 directly is idempotent
            state = get_provisioning_state(res.tenant)
            execute_step_p5_revoke_append_only(res.tenant, state)

            # Verify inside the newly provisioned schema that every one of the 6
            # append-only tables refuses UPDATE, DELETE, and TRUNCATE.
            with schema_context(schema_name):
                audit_row = AuditLogFactory(action="test.created")
                payment_row = PaymentFactory(amount=Decimal("500.00"))
                sample_event_row = SampleEventFactory(event="COLLECTED")
                report_version_row = ReportVersionFactory(version=1)
                crit_notif_row = CriticalNotificationFactory(notified_name="Dr. Ali")
                ledger_row = ShareLedgerEntryFactory(amount=Decimal("100.00"))

                records: list[tuple[str, Any, str, Any]] = [
                    ("audit_log", AuditLog, "action", audit_row),
                    ("payment", Payment, "reference", payment_row),
                    ("sample_event", SampleEvent, "note", sample_event_row),
                    ("report_version", ReportVersion, "pdf_key", report_version_row),
                    (
                        "critical_notification",
                        CriticalNotification,
                        "notified_name",
                        crit_notif_row,
                    ),
                    (
                        "share_ledger_entry",
                        ShareLedgerEntry,
                        "period",
                        ledger_row,
                    ),
                ]

                assert {r[0] for r in records} == set(TENANT_APPEND_ONLY_TABLES)

                for table_name, model_cls, field_name, instance in records:
                    # 1. UPDATE must be rejected by database
                    with pytest.raises(DatabaseError), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{schema_name}"."{table_name}" '
                            f'SET "{field_name}" = %s WHERE id = %s',
                            ["tampered", str(instance.id)],
                        )

                    # 2. DELETE must be rejected by database
                    with pytest.raises(DatabaseError), connection.cursor() as cursor:
                        cursor.execute(
                            f'DELETE FROM "{schema_name}"."{table_name}" WHERE id = %s',
                            [str(instance.id)],
                        )

                    # 3. TRUNCATE must be rejected by database
                    with pytest.raises(DatabaseError), connection.cursor() as cursor:
                        cursor.execute(f'TRUNCATE TABLE "{schema_name}"."{table_name}"')

                    # Row remains intact
                    assert model_cls.objects.filter(id=instance.id).exists() is True
        finally:
            _drop_schema_if_exists(schema_name)

    def test_p5_halts_provisioning_when_append_only_protection_is_missing_or_disabled(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "tamperedp5lab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Tampered P5 Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@tamperedp5.pk",
                        owner_name="Dr. Tamper",
                        actor_id=sa.id,
                    )
                )

            state = get_provisioning_state(res.tenant)
            execute_step_p3_create_schema(res.tenant, state)
            execute_step_p4_migrate_schema(res.tenant, state)

            # Simulate a missing/dropped append-only trigger on share_ledger_entry
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.tgname
                    FROM pg_trigger t
                    JOIN pg_class c ON c.oid = t.tgrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = %s
                      AND c.relname = 'share_ledger_entry'
                      AND NOT t.tgisinternal
                    """,
                    [schema_name],
                )
                trigger_names = [row[0] for row in cursor.fetchall()]
                assert len(trigger_names) >= 1
                for tg_name in trigger_names:
                    cursor.execute(
                        f'ALTER TABLE "{schema_name}"."share_ledger_entry" '
                        f'DISABLE TRIGGER "{tg_name}"'
                    )

            p6_called = False

            def _spy_p6(_t: Tenant, _st: ProvisioningStateSnapshot) -> None:
                nonlocal p6_called
                p6_called = True

            # Running the state machine must fail at P-5 and never reach P-6 or active
            with (
                patch.dict(
                    STEP_HANDLERS,
                    {
                        "P-3": lambda _t, _s: None,
                        "P-4": lambda _t, _s: None,
                        "P-6": _spy_p6,
                    },
                ),
                pytest.raises(
                    RuntimeError,
                    match="P-5 append-only trigger check failed",
                ),
            ):
                provision_tenant_task(slug)

            assert p6_called is False
            res.tenant.refresh_from_db()
            assert res.tenant.status == "provisioning"

            failed_state = get_provisioning_state(res.tenant)
            assert failed_state.failed_step == "P-5"
            assert failed_state.error is not None
            assert "share_ledger_entry" in failed_state.error
        finally:
            _drop_schema_if_exists(schema_name)
