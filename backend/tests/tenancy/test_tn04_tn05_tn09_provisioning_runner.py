import json
import logging
from typing import Any
from unittest.mock import patch

import pytest
from django.db import connection

from apps.core.models import Domain, PlatformAudit, Subscription, Tenant
from apps.platform.provisioning import (
    PROVISIONING_STEPS,
    STEP_HANDLERS,
    ProvisioningError,
    ProvisioningStateSnapshot,
    ProvisionTenantInput,
    cleanup_abandoned_provisioning,
    create_tenant_provisioning,
    get_provisioning_state,
)
from apps.platform.tasks import provision_tenant_task
from tests.factories import PlanFactory, PlatformUserFactory


def _schema_exists(schema_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        return cursor.fetchone() is not None


def _drop_schema_if_exists(schema_name: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


@pytest.mark.django_db(transaction=True)
class TestProvisioningResumableStateMachine:
    """Subtask 2 (KAN-73): TP-3 resumable state machine (TN-04, TN-05, TN-09)."""

    def test_tn04_provisioning_task_idempotent_and_logs_structured_json(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "nayablab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Nayab Labs",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@nayab.pk",
                        owner_name="Dr. Nayab",
                        actor_id=sa.id,
                    )
                )

            caplog.set_level(logging.INFO, logger="labflow.provisioning")
            first_run = provision_tenant_task(slug)

            assert first_run["tenant_slug"] == slug
            assert first_run["status"] == "active"
            assert first_run["resumed_noop"] is False
            for step in PROVISIONING_STEPS:
                assert step in first_run["completed_steps"]

            res.tenant.refresh_from_db()
            assert res.tenant.status == "active"
            assert _schema_exists(schema_name) is True

            # Verify structured JSON logs contain tenant_slug, step, outcome, duration
            step_logs = [
                json.loads(record.message)
                for record in caplog.records
                if record.name == "labflow.provisioning"
            ]
            assert len(step_logs) == len(PROVISIONING_STEPS)
            for idx, step_code in enumerate(PROVISIONING_STEPS):
                assert step_logs[idx]["tenant_slug"] == slug
                assert step_logs[idx]["step"] == step_code
                assert step_logs[idx]["outcome"] == "completed"
                assert isinstance(step_logs[idx]["duration_ms"], (int, float))

            # Second invocation is a no-op resume (TN-04)
            second_run = provision_tenant_task(slug)
            assert second_run["resumed_noop"] is True
            assert second_run["status"] == "active"
            assert Tenant.objects.filter(slug=slug).count() == 1
            assert Domain.objects.filter(tenant=res.tenant).count() == 1
            assert Subscription.objects.filter(tenant=res.tenant).count() == 1
        finally:
            _drop_schema_if_exists(schema_name)

    @pytest.mark.parametrize("failing_step", list(PROVISIONING_STEPS))
    def test_tn05_failure_at_each_step_stops_records_error_and_resumes_from_failed_step(
        self, failing_step: str
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        step_num = failing_step.lower().replace("-", "")
        slug = f"resumelab{step_num}"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name=f"Resume Lab {failing_step}",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email=f"owner@{slug}.pk",
                        owner_name="Dr. Resume",
                        actor_id=sa.id,
                    )
                )

            executed_first_attempt: list[str] = []
            original_handlers = dict(STEP_HANDLERS)

            def _make_TrackedHandler(step_code: str, should_fail: bool) -> Any:
                def _handler(t: Tenant, st: ProvisioningStateSnapshot) -> None:
                    executed_first_attempt.append(step_code)
                    if should_fail:
                        raise RuntimeError(f"Simulated crash at {step_code}")
                    original_handlers[step_code](t, st)

                return _handler

            patched_first = {
                s: _make_TrackedHandler(s, s == failing_step)
                for s in PROVISIONING_STEPS
            }

            with (
                patch.dict(STEP_HANDLERS, patched_first),
                pytest.raises(RuntimeError, match=f"Simulated crash at {failing_step}"),
            ):
                provision_tenant_task(slug)

            # Tenant stays in provisioning; later steps were never attempted
            res.tenant.refresh_from_db()
            assert res.tenant.status == "provisioning"
            fail_index = PROVISIONING_STEPS.index(failing_step)
            assert executed_first_attempt == list(PROVISIONING_STEPS[: fail_index + 1])

            # Failed step and error recorded on the tenant's provisioning state
            state_after_fail = get_provisioning_state(res.tenant)
            assert state_after_fail.failed_step == failing_step
            assert state_after_fail.error is not None
            assert f"Simulated crash at {failing_step}" in state_after_fail.error

            # Retry resumes at failed step without re-running completed earlier steps
            executed_second_attempt: list[str] = []

            def _make_RecoveryHandler(step_code: str) -> Any:
                def _handler(t: Tenant, st: ProvisioningStateSnapshot) -> None:
                    executed_second_attempt.append(step_code)
                    original_handlers[step_code](t, st)

                return _handler

            patched_second = {s: _make_RecoveryHandler(s) for s in PROVISIONING_STEPS}
            with patch.dict(STEP_HANDLERS, patched_second):
                retry_result = provision_tenant_task(slug)

            assert retry_result["status"] == "active"
            assert executed_second_attempt == list(PROVISIONING_STEPS[fail_index:])
            res.tenant.refresh_from_db()
            assert res.tenant.status == "active"
            final_state = get_provisioning_state(res.tenant)
            assert final_state.failed_step is None
            assert final_state.error is None
        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn09_abandoned_provisioning_cleanup_drops_schema_and_deletes_domains(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "abandonedlab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Abandoned Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@abandoned.pk",
                        owner_name="Dr. Abandoned",
                        actor_id=sa.id,
                    )
                )

            # Simulate failing at P-4 after P-3 created the schema
            original_p4 = STEP_HANDLERS["P-4"]

            def _crash_p4(_t: Tenant, _st: ProvisioningStateSnapshot) -> None:
                raise RuntimeError("P-4 halted")

            with (
                patch.dict(STEP_HANDLERS, {"P-4": _crash_p4}),
                pytest.raises(RuntimeError, match="P-4 halted"),
            ):
                provision_tenant_task(slug)
            _ = original_p4

            assert _schema_exists(schema_name) is True
            assert Domain.objects.filter(tenant=res.tenant).exists() is True

            # Execute abandoned cleanup (Doc 04 §4.2, §5.2 — TN-09)
            cleaned_tenant = cleanup_abandoned_provisioning(slug, actor_id=sa.id)
            assert cleaned_tenant.status == "deleted"
            assert _schema_exists(schema_name) is False
            assert Domain.objects.filter(tenant=res.tenant).exists() is False

            # Tenant registry row and full audit history remain
            assert Tenant.objects.filter(id=res.tenant.id, status="deleted").exists()
            audit_actions = list(
                PlatformAudit.objects.filter(entity_id=res.tenant.id)
                .order_by("at", "id")
                .values_list("action", flat=True)
            )
            assert "tenant.created" in audit_actions
            assert "tenant.provisioning_failed" in audit_actions
            assert "tenant.abandoned_cleaned_up" in audit_actions

            # Active tenants cannot be cleaned up as abandoned
            with pytest.raises(ProvisioningError) as exc_info:
                cleanup_abandoned_provisioning(slug, actor_id=sa.id)
            assert exc_info.value.code == "invalid_state_transition"
            assert exc_info.value.status_code == 409
        finally:
            _drop_schema_if_exists(schema_name)
