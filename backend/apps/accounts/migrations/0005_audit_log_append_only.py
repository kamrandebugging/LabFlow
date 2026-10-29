from django.conf import settings
from django.db import connection, migrations


def get_db_user() -> str:
    user = connection.settings_dict.get("USER")
    if not user and hasattr(settings, "DATABASES"):
        user = settings.DATABASES.get("default", {}).get("USER")
    return str(user or "labflow_app")


DB_USER = get_db_user()

REVOKE_SQL = f"""
CREATE OR REPLACE FUNCTION prevent_append_only_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table is append-only: UPDATE, DELETE, and TRUNCATE are prohibited.';
END;
$$ LANGUAGE plpgsql;

REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "audit_log" FROM "{DB_USER}";

DROP TRIGGER IF EXISTS "trg_append_only_audit_log" ON "audit_log";
CREATE TRIGGER "trg_append_only_audit_log"
BEFORE UPDATE OR DELETE OR TRUNCATE ON "audit_log"
FOR EACH STATEMENT EXECUTE FUNCTION prevent_append_only_mutation();
"""

RESTORE_SQL = f"""
DROP TRIGGER IF EXISTS "trg_append_only_audit_log" ON "audit_log";
GRANT UPDATE, DELETE, TRUNCATE ON TABLE "audit_log" TO "{DB_USER}";
"""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_auditlog"),
    ]

    operations = [
        migrations.RunSQL(
            sql=REVOKE_SQL,
            reverse_sql=RESTORE_SQL,
        ),
    ]
