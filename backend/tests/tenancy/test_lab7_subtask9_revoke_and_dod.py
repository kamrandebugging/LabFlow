from importlib import import_module
from typing import Any

import pytest
from django.apps import apps
from django.db import connection
from django_tenants.utils import tenant_context

import tests.factories as factories_pkg
from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.catalog.models import (
    Panel,
    PanelTest,
    ReferenceRange,
    Test,
    TestPrice,
)
from apps.patients.models import Patient, PatientConsent, PatientContact
from apps.reports.models import (
    Report,
    ReportAccessToken,
    ReportDelivery,
    ReportVersion,
)
from apps.results.models import CriticalNotification, Result, ResultApproval
from apps.samples.models import Sample, SampleEvent, SampleTest, SampleTransfer
from tests.factories.base import TenantModelFactory

revoke_migration_module = import_module(
    "apps.reports.migrations.0002_clinical_append_only_revoke"
)

LAB7_APPEND_ONLY_TABLES = (
    "payment",
    "sample_event",
    "report_version",
    "critical_notification",
)

LAB7_MUTABLE_TABLES = (
    "patient",
    "patient_contact",
    "patient_consent",
    "test",
    "panel",
    "panel_test",
    "test_price",
    "reference_range",
    "invoice",
    "invoice_item",
    "sample",
    "sample_test",
    "sample_transfer",
    "result",
    "result_approval",
    "report",
    "report_delivery",
    "report_access_token",
)

LAB7_22_MODELS = (
    Patient,
    PatientContact,
    PatientConsent,
    Test,
    Panel,
    PanelTest,
    TestPrice,
    ReferenceRange,
    Invoice,
    InvoiceItem,
    Payment,
    Sample,
    SampleTest,
    SampleEvent,
    SampleTransfer,
    Result,
    ResultApproval,
    CriticalNotification,
    Report,
    ReportVersion,
    ReportDelivery,
    ReportAccessToken,
)


def _table_privileges(schema_name: str, table_name: str) -> set[str]:
    """
    Return the set of table privileges explicitly granted to current_user
    in information_schema.role_table_grants for (schema_name, table_name).
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
class TestLab7Subtask9RevokeAndDoD:
    def test_append_only_privileges_revoked_in_tenant_schemas(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        for tenant in (tenant_a, tenant_b):
            with tenant_context(tenant):
                for table_name in LAB7_APPEND_ONLY_TABLES:
                    grants = _table_privileges(tenant.schema_name, table_name)
                    assert "SELECT" in grants, (
                        f"SELECT missing on {table_name} in {tenant.schema_name}"
                    )
                    assert "INSERT" in grants, (
                        f"INSERT missing on {table_name} in {tenant.schema_name}"
                    )
                    assert "UPDATE" not in grants, (
                        f"UPDATE still granted on {table_name} in {tenant.schema_name}"
                    )
                    assert "DELETE" not in grants, (
                        f"DELETE still granted on {table_name} in {tenant.schema_name}"
                    )
                    assert "TRUNCATE" not in grants, (
                        f"TRUNCATE still granted on {table_name} in "
                        f"{tenant.schema_name}"
                    )

    def test_nothing_revoked_beyond_doc02_section6_list(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            for table_name in LAB7_MUTABLE_TABLES:
                grants = _table_privileges(tenant_a.schema_name, table_name)
                assert "SELECT" in grants
                assert "INSERT" in grants
                assert "UPDATE" in grants, (
                    f"Mutable table {table_name} unexpectedly lost UPDATE privilege"
                )
                assert "DELETE" in grants, (
                    f"Mutable table {table_name} unexpectedly lost DELETE privilege"
                )

    def test_revoke_migration_is_reversible(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            with connection.schema_editor() as editor:
                revoke_migration_module.reverse_append_only_revoke(apps, editor)

            for table_name in LAB7_APPEND_ONLY_TABLES:
                grants = _table_privileges(tenant_a.schema_name, table_name)
                assert {
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                }.issubset(grants)

            with connection.schema_editor() as editor:
                revoke_migration_module.apply_append_only_revoke(apps, editor)

            for table_name in LAB7_APPEND_ONLY_TABLES:
                grants = _table_privileges(tenant_a.schema_name, table_name)
                assert "SELECT" in grants
                assert "INSERT" in grants
                assert "UPDATE" not in grants
                assert "DELETE" not in grants
                assert "TRUNCATE" not in grants

    def test_all_22_lab7_models_have_factories_and_isolation_coverage(
        self, tenant_a: Any
    ) -> None:
        assert len(LAB7_22_MODELS) == 22

        # Collect all TenantModelFactory subclasses exported in tests.factories
        exported_factories = {}
        for attr_name in dir(factories_pkg):
            obj = getattr(factories_pkg, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, TenantModelFactory)
                and obj is not TenantModelFactory
            ):
                model_cls = obj._meta.model
                exported_factories[model_cls] = obj

        with tenant_context(tenant_a):
            for model_cls in LAB7_22_MODELS:
                assert model_cls in exported_factories, (
                    f"Missing factory in tests.factories for {model_cls.__name__}"
                )
                factory_cls = exported_factories[model_cls]
                instance = factory_cls()
                assert instance.pk is not None
