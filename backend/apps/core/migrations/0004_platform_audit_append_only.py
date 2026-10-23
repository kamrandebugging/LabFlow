"""Enforce append-only permissions on platform_audit table per Doc 02 §6.

Grants SELECT and INSERT and revokes UPDATE, DELETE, and TRUNCATE from the
configured application database role.
"""

from typing import Any

from django.conf import settings
from django.db import migrations


def get_forward_sql(schema_editor: Any) -> str:
    """Generate forward SQL granting SELECT, INSERT and revoking UPDATE, DELETE, TRUNCATE."""
    db_user = settings.DATABASES.get("default", {}).get("USER") or "labflow_app"
    quoted_role = schema_editor.connection.ops.quote_name(db_user)
    return f"""
    GRANT SELECT, INSERT ON platform_audit TO {quoted_role};
    REVOKE UPDATE, DELETE, TRUNCATE ON platform_audit FROM {quoted_role};
    """


def get_reverse_sql(schema_editor: Any) -> str:
    """Generate reverse SQL restoring all original table privileges."""
    db_user = settings.DATABASES.get("default", {}).get("USER") or "labflow_app"
    quoted_role = schema_editor.connection.ops.quote_name(db_user)
    return f"""
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON platform_audit TO {quoted_role};
    """


# Support callables in RunSQL operations
_orig_run_sql: Any = getattr(
    migrations.RunSQL, "_orig_run_sql", getattr(migrations.RunSQL, "_run_sql", None)
)
setattr(migrations.RunSQL, "_orig_run_sql", _orig_run_sql)  # noqa: B010


def _callable_run_sql(self: Any, schema_editor: Any, sqls: Any) -> None:
    if callable(sqls):
        sqls = sqls(schema_editor)
    if _orig_run_sql is not None:
        _orig_run_sql(self, schema_editor, sqls)


setattr(migrations.RunSQL, "_run_sql", _callable_run_sql)  # noqa: B010


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_platform_user_audit"),
    ]

    operations = [
        migrations.RunSQL(
            sql=get_forward_sql,  # type: ignore[arg-type]
            reverse_sql=get_reverse_sql,  # type: ignore[arg-type]
        ),
    ]
