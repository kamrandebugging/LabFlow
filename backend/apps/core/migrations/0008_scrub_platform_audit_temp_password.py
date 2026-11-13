"""D6: scrub plaintext temporary passwords from the platform audit trail.

``tenant.created`` audit rows used to persist the provisioning credential in
``after_jsonb["temp_password"]``. New writes no longer include it; this data
migration removes the key from every existing row (before and after payloads).

``platform_audit`` is append-only for the application role (migration 0004),
so the scrub temporarily grants UPDATE to the migration connection and revokes
it again afterwards, restoring the append-only posture.
"""

from typing import Any

from django.conf import settings
from django.db import migrations


def scrub_temp_passwords(apps: Any, schema_editor: Any) -> int:
    """Remove ``temp_password`` keys and return the number of rows scrubbed."""
    connection = schema_editor.connection
    # 0004 revoked UPDATE from the configured application role, so the scrub
    # must restore that exact role's privilege, not whichever role happens to
    # run migrations.
    db_user = settings.DATABASES.get("default", {}).get("USER")
    if not db_user:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user;")
            row = cursor.fetchone()
        if not row:
            return 0
        db_user = str(row[0])
    quoted_user = schema_editor.quote_name(db_user)

    schema_editor.execute(f"GRANT UPDATE ON platform_audit TO {quoted_user};")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE platform_audit
                   SET before_jsonb = CASE
                           WHEN before_jsonb ? 'temp_password'
                           THEN before_jsonb - 'temp_password'
                           ELSE before_jsonb
                       END,
                       after_jsonb = CASE
                           WHEN after_jsonb ? 'temp_password'
                           THEN after_jsonb - 'temp_password'
                           ELSE after_jsonb
                       END
                 WHERE (before_jsonb ? 'temp_password')
                    OR (after_jsonb ? 'temp_password')
                """
            )
            scrubbed = cursor.rowcount
    except Exception:
        # Keep the original failure: an aborted transaction must not be
        # masked by a follow-up REVOKE error.
        print("D6: temp_password scrub failed; audit rows left unchanged")
        raise
    else:
        schema_editor.execute(
            f"REVOKE UPDATE ON platform_audit FROM {quoted_user};"
        )
    print(f"D6: scrubbed temp_password from {scrubbed} platform_audit row(s)")
    return scrubbed


def noop_reverse(apps: Any, schema_editor: Any) -> None:
    """The plaintext credential is intentionally unrecoverable."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_platform_dashboard_phase2"),
    ]

    operations = [
        migrations.RunPython(scrub_temp_passwords, noop_reverse),
    ]
