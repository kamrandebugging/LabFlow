from django.conf import settings
from django.db import connection, migrations


def get_db_user() -> str:
    user = connection.settings_dict.get("USER")
    if not user and hasattr(settings, "DATABASES"):
        user = settings.DATABASES.get("default", {}).get("USER")
    return str(user or "labflow_app")


DB_USER = get_db_user()

REVOKE_SQL = f'REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "audit_log" FROM "{DB_USER}";'
RESTORE_SQL = f'GRANT UPDATE, DELETE, TRUNCATE ON TABLE "audit_log" TO "{DB_USER}";'


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
