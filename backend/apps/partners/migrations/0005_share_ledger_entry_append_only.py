from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import connection, migrations


def get_db_user() -> str:
    user = connection.settings_dict.get("USER")
    if not user and hasattr(settings, "DATABASES"):
        user = settings.DATABASES.get("default", {}).get("USER")
    return str(user or "labflow_app")


DB_USER = get_db_user()

REVOKE_SQL = f"""
DO $$
DECLARE
    r text;
BEGIN
    FOR r IN
        SELECT rolname FROM pg_roles
        WHERE rolname IN ('{DB_USER}', 'labflow_app', current_user)
    LOOP
        EXECUTE 'GRANT SELECT, INSERT ON TABLE "share_ledger_entry" TO ' || quote_ident(r);
        EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "share_ledger_entry" FROM ' || quote_ident(r);
    END LOOP;
END
$$;
"""

RESTORE_SQL = f"""
DO $$
DECLARE
    r text;
BEGIN
    FOR r IN
        SELECT rolname FROM pg_roles
        WHERE rolname IN ('{DB_USER}', 'labflow_app', current_user)
    LOOP
        EXECUTE 'GRANT UPDATE, DELETE, TRUNCATE ON TABLE "share_ledger_entry" TO ' || quote_ident(r);
    END LOOP;
END
$$;
"""


def apply_append_only_revoke(apps: Any, schema_editor: Any) -> None:
    """Revoke UPDATE, DELETE, and TRUNCATE on share_ledger_entry (Doc 02 §6)

    in tenant schema while keeping SELECT and INSERT granted.
    """
    connection = schema_editor.connection
    if getattr(connection, "schema_name", "public") == "public":
        return
    schema_editor.execute(REVOKE_SQL)


def reverse_append_only_revoke(apps: Any, schema_editor: Any) -> None:
    """Restore UPDATE, DELETE, and TRUNCATE privileges on rollback."""
    connection = schema_editor.connection
    if getattr(connection, "schema_name", "public") == "public":
        return
    schema_editor.execute(RESTORE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0004_settlement_and_settlement_line"),
    ]

    operations = [
        migrations.RunSQL(
            sql=REVOKE_SQL,
            reverse_sql=RESTORE_SQL,
        ),
    ]
