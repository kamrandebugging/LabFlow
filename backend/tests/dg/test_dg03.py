"""Scenario DG-03 skeleton test per Doc 09 §18.

Verbatim from Doc 09 §18:
Scenario: Add a model field without a migration
Expected: makemigrations --check fails (§7.5)
"""

from __future__ import annotations

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import connection, models
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from django_tenants.utils import schema_context

from tests.factories.tenants import TenantFactory
from tests.fixtures.tenants import TenantFixture


@pytest.mark.dg
def test_dg03_makemigrations_check_fails_on_unmigrated_field(
    tenant_a: TenantFixture,
) -> None:
    """DG-03: Verify unmigrated model changes are detected per Doc 09 §7.5."""
    # 1. Harness-level assertion: build tenant record using Subtask 3 TenantFactory
    ephemeral_tenant = TenantFactory.build()
    assert ephemeral_tenant.schema_name.startswith("tenant_fac_")

    with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ready;")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1

    # 2. Gate check part A: baseline repository has zero unmigrated model changes
    # call_command('makemigrations', check=True, dry_run=True) exits cleanly
    call_command("makemigrations", check=True, dry_run=True)

    # 3. Gate check part B: verify MigrationAutodetector flags unmigrated fields
    loader = MigrationLoader(connection)
    current_state = ProjectState.from_apps(apps)

    # Clone project state and simulate adding an unmigrated field to a managed model
    simulated_state = current_state.clone()
    app_models = [m for m in apps.get_models() if m._meta.managed]

    if app_models:
        target_model = app_models[0]
        model_key = (
            target_model._meta.app_label,
            target_model.__name__.lower(),
        )
        model_state = simulated_state.models[model_key]
        model_state.fields["unmigrated_audit_flag"] = models.BooleanField(default=False)

        autodetector = MigrationAutodetector(current_state, simulated_state)
        changes = autodetector.changes(graph=loader.graph)

        assert target_model._meta.app_label in changes
        assert any(
            "unmigrated_audit_flag" in str(op)
            for migration in changes[target_model._meta.app_label]
            for op in migration.operations
        )
    else:
        # Before domain models exist at LAB-4, verify MigrationAutodetector operates
        autodetector = MigrationAutodetector(current_state, current_state)
        assert not autodetector.changes(graph=loader.graph)

    # Full scenario with LAB-5 domain models is completed in LAB-15.
