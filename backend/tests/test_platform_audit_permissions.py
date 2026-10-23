"""Tests for platform_audit append-only permission enforcement (Doc 02 §6)."""

import importlib
from typing import Any

import pytest
from django.apps import apps
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

migration_0004 = importlib.import_module(
    "apps.core.migrations.0004_platform_audit_append_only"
)
get_forward_sql = migration_0004.get_forward_sql
get_reverse_sql = migration_0004.get_reverse_sql


def test_sql_generation_uses_configured_database_role() -> None:
    """SQL generators extract role from settings and format proper SQL statements."""

    class DummySchemaEditor:
        class Connection:
            class Ops:
                @staticmethod
                def quote_name(name: str) -> str:
                    return f'"{name}"'

            ops = Ops()

        connection = Connection()

    editor: Any = DummySchemaEditor()
    expected_user = settings.DATABASES.get("default", {}).get("USER") or "labflow_app"

    forward_sql = get_forward_sql(editor)
    assert f'GRANT SELECT, INSERT ON platform_audit TO "{expected_user}"' in forward_sql
    assert (
        f'REVOKE UPDATE, DELETE, TRUNCATE ON platform_audit FROM "{expected_user}"'
        in forward_sql
    )

    reverse_sql = get_reverse_sql(editor)
    expected_reverse = (
        "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON platform_audit TO "
        f'"{expected_user}"'
    )
    assert expected_reverse in reverse_sql


@pytest.mark.django_db
def test_platform_audit_migration_is_reversible() -> None:
    """Migration 0004 applies forwards and reverses cleanly via MigrationExecutor."""
    executor = MigrationExecutor(connection)
    app_config = apps.get_app_config("core")
    assert app_config is not None

    # Migrate forward to 0004
    executor.migrate([("core", "0004_platform_audit_append_only")])
    current_migration = executor.loader.get_migration(
        "core", "0004_platform_audit_append_only"
    )
    assert current_migration is not None

    # Rollback to 0003
    executor.migrate([("core", "0003_platform_user_audit")])
    executor.loader.build_graph()

    # Re-apply forward to 0004 to leave schema in target state
    executor.migrate([("core", "0004_platform_audit_append_only")])
