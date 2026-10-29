import json
import logging
from unittest.mock import patch

import pytest
from django.core import mail
from django.db import connection

from apps.core.models import PlatformAudit, Tenant
from apps.platform.provisioning import (
    ProvisioningError,
    ProvisionTenantInput,
    create_tenant_provisioning,
    execute_step_p3_create_schema,
    execute_step_p4_migrate_schema,
    execute_step_p8_create_owner,
    execute_step_p9_activate,
    get_provisioning_state,
)
from apps.platform.tasks import provision_tenant_task
from tests.factories import PlanFactory, PlatformUserFactory


def _drop_schema_if_exists(schema_name: str) -> None:
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


@pytest.mark.django_db(transaction=True)
class TestStepP9TenantActivationAndAudit:
    """
    Subtask 7 (Story KAN-53 / Epic LAB-9 — TN-10):
    P-9 flips status from provisioning to active in the public schema guarded on
    status='provisioning', writes the platform_audit row (tenant.provisioned)
    with total duration and per-step outcome summary, and logs total duration.
    """

    def test_tn10_p9_flips_status_to_active_and_writes_audit(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "p9activatelab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="P9 Activate Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@p9activate.pk",
                        owner_name="Dr. Activate",
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            assert tenant.status == "provisioning"

            state = get_provisioning_state(tenant)
            execute_step_p3_create_schema(tenant, state)
            execute_step_p4_migrate_schema(tenant, state)
            execute_step_p8_create_owner(tenant, state)

            mail_count_before_p9 = len(mail.outbox)
            execute_step_p9_activate(tenant, state)

            # 1. Tenant status is now active
            tenant.refresh_from_db()
            assert tenant.status == "active"

            # 2. No email sent or external certificate calls during P-9
            assert len(mail.outbox) == mail_count_before_p9

            # 3. Platform audit row written for tenant.provisioned
            audits = PlatformAudit.objects.filter(
                entity_type="tenant",
                entity_id=tenant.id,
                action="tenant.provisioned",
            )
            assert audits.count() == 1
            audit_record = audits.first()
            assert audit_record is not None
            assert audit_record.before_jsonb == {"status": "provisioning"}
            assert isinstance(audit_record.after_jsonb, dict)
            assert audit_record.after_jsonb["status"] == "active"
            assert audit_record.after_jsonb["tenant_slug"] == slug
            assert isinstance(
                audit_record.after_jsonb["total_duration_ms"], (int, float)
            )
            assert audit_record.after_jsonb["total_duration_ms"] >= 0.0

            # 4. Per-step outcome summary includes P-9
            step_summary = audit_record.after_jsonb["step_summary"]
            assert isinstance(step_summary, dict)
            assert "P-9" in step_summary
            assert step_summary["P-9"]["outcome"] == "completed"

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn10_p9_refuses_already_active_tenant_with_409(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "p9activestate"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="P9 Active State Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@activestate.pk",
                        owner_name="Dr. ActiveState",
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            # Manually force tenant to active status to simulate concurrent activation
            Tenant.objects.filter(id=tenant.id).update(status="active")
            tenant.refresh_from_db()
            assert tenant.status == "active"

            state = get_provisioning_state(tenant)
            with pytest.raises(ProvisioningError) as exc_info:
                execute_step_p9_activate(tenant, state)

            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "invalid_state_transition"
            assert "must be 'provisioning'" in exc_info.value.detail

            # Tenant status unchanged
            tenant.refresh_from_db()
            assert tenant.status == "active"

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn10_p9_refuses_suspended_tenant_with_409(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "p9suspendedlab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="P9 Suspended Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@suspended.pk",
                        owner_name="Dr. Suspended",
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            Tenant.objects.filter(id=tenant.id).update(status="suspended")
            tenant.refresh_from_db()
            assert tenant.status == "suspended"

            state = get_provisioning_state(tenant)
            with pytest.raises(ProvisioningError) as exc_info:
                execute_step_p9_activate(tenant, state)

            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "invalid_state_transition"
            assert "status must be 'provisioning'" in exc_info.value.detail

            # Tenant remains suspended; lifecycle must not be corrupted (LAB-48)
            tenant.refresh_from_db()
            assert tenant.status == "suspended"

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn10_p9_refuses_deleted_tenant_with_409(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "p9deletedlab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="P9 Deleted Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@deleted.pk",
                        owner_name="Dr. Deleted",
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            Tenant.objects.filter(id=tenant.id).update(status="deleted")
            tenant.refresh_from_db()

            state = get_provisioning_state(tenant)
            with pytest.raises(ProvisioningError) as exc_info:
                execute_step_p9_activate(tenant, state)

            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "invalid_state_transition"

            tenant.refresh_from_db()
            assert tenant.status == "deleted"

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn10_full_task_logs_total_duration_with_tenant_slug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "p9logchecklab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="P9 Log Check Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@logcheck.pk",
                        owner_name="Dr. Logger",
                        actor_id=sa.id,
                    )
                )

            caplog.set_level(logging.INFO, logger="labflow.provisioning")
            task_res = provision_tenant_task(slug)
            assert task_res["status"] == "active"

            # Check that P-9 log line contains total_duration_ms and tenant_slug
            # (G4 measurement against the 3-minute target)
            p9_logs = [
                json.loads(record.message)
                for record in caplog.records
                if record.name == "labflow.provisioning"
                and '"step": "P-9"' in record.message
            ]
            assert len(p9_logs) == 1
            log_line = p9_logs[0]
            assert log_line["tenant_slug"] == slug
            assert log_line["step"] == "P-9"
            assert log_line["outcome"] == "completed"
            assert "total_duration_ms" in log_line
            assert isinstance(log_line["total_duration_ms"], (int, float))
            assert log_line["total_duration_ms"] > 0

        finally:
            _drop_schema_if_exists(schema_name)
