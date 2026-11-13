"""Never store the provisioning credential in plaintext (owner-ordered).

The credential is shown once in the provisioning response. The registry keeps
only its Argon2 hash (used by the async provisioning task to create the owner
login) and the plaintext column stays empty. This migration hashes any
remaining plaintext for in-flight tenants and drops it outright for tenants
whose owner has already changed the temporary password.
"""

from typing import Any

from django.contrib.auth.hashers import make_password
from django.db import migrations, models, transaction
from django_tenants.utils import schema_context


def _owner_changed_password(apps: Any, schema_name: str) -> bool:
    """True when the tenant's owner is no longer on the temporary password."""
    try:
        # Savepoint: a missing/partially-migrated tenant schema must not abort
        # the shared-schema migration transaction.
        with transaction.atomic(), schema_context(schema_name):
            owner = (
                apps.get_model("accounts", "StaffUser")
                .objects.filter(role="owner")
                .order_by("created_at")
                .first()
            )
    except Exception:
        # Schema not created yet (still provisioning): keep the hash so the
        # owner-creation step can consume it.
        return False
    return owner is not None and not owner.password_is_temporary


def _scrub_rows(apps: Any, schema_editor: Any) -> int:
    connection = schema_editor.connection
    if getattr(connection, "schema_name", "public") != "public":
        return 0

    Tenant = apps.get_model("core", "Tenant")
    scrubbed = 0
    for tenant in Tenant.objects.exclude(temp_password=""):
        plaintext = tenant.temp_password
        if not plaintext:
            continue
        if _owner_changed_password(apps, tenant.schema_name):
            update: dict[str, Any] = {
                "temp_password": "",
                "temp_password_hash": "",
                "temp_password_expires_at": None,
            }
        else:
            update = {
                "temp_password": "",
                "temp_password_hash": make_password(plaintext),
            }
        Tenant.objects.filter(pk=tenant.pk).update(**update)
        scrubbed += 1
    print(f"temp-password scrub: cleared plaintext from {scrubbed} tenant row(s)")
    return scrubbed


def scrub_plaintext_temp_passwords(apps: Any, schema_editor: Any) -> None:
    _scrub_rows(apps, schema_editor)


def noop_reverse(apps: Any, schema_editor: Any) -> None:
    """The plaintext credential is intentionally unrecoverable."""


class Migration(migrations.Migration):
    # ``core`` is a SHARED_APP and ``accounts`` is a TENANT_APP: a shared
    # migration must not depend on a tenant migration (django-tenants applies
    # them to different schemas, and the test harness purges tenant-app rows
    # from the public recorder, which makes the graph inconsistent). The
    # backfill below tolerates a tenant schema whose accounts tables are not
    # migrated yet by keeping the hash for the owner-creation step.
    dependencies = [
        ("core", "0008_scrub_platform_audit_temp_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="temp_password_hash",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Argon2 hash of the provisioning-issued credential, used "
                    "once to create the owner login; cleared on first "
                    "login/password change."
                ),
                max_length=255,
            ),
        ),
        migrations.RunPython(scrub_plaintext_temp_passwords, noop_reverse),
    ]
