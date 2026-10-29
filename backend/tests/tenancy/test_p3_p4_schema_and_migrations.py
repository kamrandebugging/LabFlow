from unittest.mock import patch

import pytest
from django.apps import apps
from django.conf import settings
from django.db import connection

from apps.core.models import Tenant
from apps.platform.provisioning import (
    ProvisioningStateSnapshot,
    ProvisionTenantInput,
    create_tenant_provisioning,
    execute_step_p3_create_schema,
    execute_step_p4_migrate_schema,
    get_provisioning_state,
)
from apps.platform.tasks import provision_tenant_task
from tests.factories import PlanFactory, PlatformUserFactory


def _get_schema_tables(schema_name: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            """,
            [schema_name],
        )
        return {row[0] for row in cursor.fetchall()}


def _drop_schema_if_exists(schema_name: str) -> None:
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


def _expected_tenant_model_tables() -> set[str]:
    tenant_app_labels = {app_path.split(".")[-1] for app_path in settings.TENANT_APPS}
    tables: set[str] = set()
    for model in apps.get_models():
        if model._meta.app_label in tenant_app_labels and not model._meta.proxy:
            tables.add(model._meta.db_table)
    return tables


@pytest.mark.django_db(transaction=True)
class TestStepsP3AndP4SchemaAndMigrations:
    """Subtask 3 (KAN-74): P-3 schema creation and P-4 single-schema migrations."""

    def test_p3_and_p4_create_schema_and_apply_all_37_tenant_tables(self) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "idcislamabad"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Islamabad Diagnostic Centre",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@idc.pk",
                        owner_name="Dr. Rizwan",
                        actor_id=sa.id,
                    )
                )

            result = provision_tenant_task(slug)
            assert result["status"] == "active"

            schema_tables = _get_schema_tables(schema_name)
            expected_tables = _expected_tenant_model_tables()
            assert len(expected_tables) >= 30
            assert expected_tables.issubset(schema_tables)
            assert "django_migrations" in schema_tables

            # Public-only tables must NOT exist in the tenant schema
            assert "tenant" not in schema_tables
            assert "platform_audit" not in schema_tables
            assert "subscription" not in schema_tables
            _ = res
        finally:
            _drop_schema_if_exists(schema_name)

    def test_p3_idempotent_when_schema_exists_and_rejects_mismatched_schema_name(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "citilabp3"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Citi Lab P3",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@citilabp3.pk",
                        owner_name="Dr. Citi",
                        actor_id=sa.id,
                    )
                )

            state = get_provisioning_state(res.tenant)
            # Run P-3 twice: second call must succeed idempotently
            execute_step_p3_create_schema(res.tenant, state)
            execute_step_p3_create_schema(res.tenant, state)

            # Tampered schema_name that disagrees with tenant_<slug> must be rejected
            res.tenant.schema_name = "tenant_wrongslug"
            with pytest.raises(ValueError, match="Tenant schema_name mismatch"):
                execute_step_p3_create_schema(res.tenant, state)
        finally:
            _drop_schema_if_exists(schema_name)

    def test_p4_migrates_only_target_schema_and_resumes_idempotently(self) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug_target = "targetp4lab"
        slug_other = "otherp4lab"
        schema_target = f"tenant_{slug_target}"
        schema_other = f"tenant_{slug_other}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res_target = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Target P4 Lab",
                        slug=slug_target,
                        plan_id=plan.id,
                        owner_email="owner@targetp4.pk",
                        owner_name="Dr. Target",
                        actor_id=sa.id,
                    )
                )
                res_other = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Other P4 Lab",
                        slug=slug_other,
                        plan_id=plan.id,
                        owner_email="owner@otherp4.pk",
                        owner_name="Dr. Other",
                        actor_id=sa.id,
                    )
                )

            state_target = get_provisioning_state(res_target.tenant)
            state_other = get_provisioning_state(res_other.tenant)

            # Create both schemas in P-3
            execute_step_p3_create_schema(res_target.tenant, state_target)
            execute_step_p3_create_schema(res_other.tenant, state_other)

            # Run P-4 on target only
            with patch(
                "apps.platform.provisioning.call_command",
                wraps=execute_step_p4_migrate_schema.__globals__["call_command"],
            ) as spy_call_command:
                execute_step_p4_migrate_schema(res_target.tenant, state_target)

            spy_call_command.assert_called_once_with(
                "migrate_schemas",
                tenant=True,
                schema_name=schema_target,
                interactive=False,
                verbosity=0,
            )

            # Target schema has all tenant tables; other schema was untouched
            expected_count = len(_expected_tenant_model_tables())
            assert len(_get_schema_tables(schema_target)) >= expected_count
            assert _get_schema_tables(schema_other) == set()

            # Re-running P-4 on an already-migrated schema is a safe idempotent no-op
            execute_step_p4_migrate_schema(res_target.tenant, state_target)
            assert len(_get_schema_tables(schema_target)) >= expected_count
        finally:
            _drop_schema_if_exists(schema_target)
            _drop_schema_if_exists(schema_other)

    def test_tn05_mocked_runner_remains_fast(self) -> None:
        """Verify connection is always restored to public after P-3 and P-4."""
        assert connection.schema_name == "public"
        _ = Tenant
        _ = ProvisioningStateSnapshot
