from typing import Any

from django.db import migrations

APPEND_ONLY_TABLES = (
    "payment",
    "sample_event",
    "report_version",
    "critical_notification",
)


def apply_append_only_revoke(apps: Any, schema_editor: Any) -> None:
    """
    Revoke UPDATE, DELETE, and TRUNCATE on the four LAB-7 append-only tables
    (payment, sample_event, report_version, critical_notification) in every
    tenant schema while keeping SELECT and INSERT granted (Doc 02 §6).
    Never runs in the public schema.
    """
    connection = schema_editor.connection
    if getattr(connection, "schema_name", "public") == "public":
        return

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user;")
        row = cursor.fetchone()
        if not row:
            return
        db_user = row[0]

    quoted_user = schema_editor.quote_name(db_user)
    for table_name in APPEND_ONLY_TABLES:
        quoted_table = schema_editor.quote_name(table_name)
        schema_editor.execute(
            f"GRANT SELECT, INSERT ON TABLE {quoted_table} TO {quoted_user};"
        )
        schema_editor.execute(
            f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {quoted_table} FROM {quoted_user};"
        )


def reverse_append_only_revoke(apps: Any, schema_editor: Any) -> None:
    """
    Restore UPDATE, DELETE, and TRUNCATE privileges on rollback.
    """
    connection = schema_editor.connection
    if getattr(connection, "schema_name", "public") == "public":
        return

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user;")
        row = cursor.fetchone()
        if not row:
            return
        db_user = row[0]

    quoted_user = schema_editor.quote_name(db_user)
    for table_name in APPEND_ONLY_TABLES:
        quoted_table = schema_editor.quote_name(table_name)
        schema_editor.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLE {quoted_table} TO {quoted_user};"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_payment"),
        ("samples", "0001_initial"),
        ("results", "0001_initial"),
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            code=apply_append_only_revoke,
            reverse_code=reverse_append_only_revoke,
        ),
    ]
