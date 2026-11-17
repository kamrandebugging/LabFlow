"""Delete stored reset requests for emails that do not exist in the tenant.

Gap 2: the public ``staff-request`` endpoint must never store a request for an
unknown address (it still answers 202). Earlier rows may already contain such
addresses; this data fix removes them per tenant schema without touching the
applied 0010 migration.
"""

from typing import Any

from django.db import migrations


def _purge_orphans(apps: Any, schema_editor: Any) -> None:
    connection = schema_editor.connection
    # accounts is a TENANT_APP; never run this against the public schema.
    if getattr(connection, "schema_name", "public") == "public":
        return

    StaffPasswordResetRequest = apps.get_model("accounts", "StaffPasswordResetRequest")
    StaffUser = apps.get_model("accounts", "StaffUser")

    known_emails = {
        email.strip().lower()
        for email in StaffUser.objects.values_list("email", flat=True)
        if email
    }
    orphan_ids = [
        row.pk
        for row in StaffPasswordResetRequest.objects.only("pk", "email")
        if (row.email or "").strip().lower() not in known_emails
    ]
    if orphan_ids:
        StaffPasswordResetRequest.objects.filter(pk__in=orphan_ids).delete()


def _noop_reverse(apps: Any, schema_editor: Any) -> None:
    """Deleting unknown-address rows is not reversible (and should not be)."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_staff_password_reset_request"),
    ]

    operations = [
        migrations.RunPython(_purge_orphans, _noop_reverse),
    ]
