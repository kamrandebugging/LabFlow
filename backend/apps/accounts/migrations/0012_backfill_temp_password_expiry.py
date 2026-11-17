"""Backfill a 24-hour expiry for legacy temporary passwords (Gap review).

Rows created before ``temp_password_expires_at`` existed (or by paths that
forgot to stamp it) had ``password_is_temporary=True`` but a NULL expiry,
which the login check treats as "no expiry". This data fix stamps the issue
window as ``created_at + 24h``; already-old rows become expired and must be
reset, which is the safe direction.
"""

from datetime import timedelta
from typing import Any

from django.db import migrations
from django.db.models import F


def _backfill_expiry(apps: Any, schema_editor: Any) -> None:
    if getattr(schema_editor.connection, "schema_name", "public") == "public":
        return

    StaffUser = apps.get_model("accounts", "StaffUser")
    # Anchor on creation time: an already-old temporary password expires
    # rather than receiving a fresh 24-hour window.
    StaffUser.objects.filter(
        password_is_temporary=True,
        temp_password_expires_at__isnull=True,
    ).update(temp_password_expires_at=F("created_at") + timedelta(hours=24))


def _noop_reverse(apps: Any, schema_editor: Any) -> None:
    """The previous NULL (never-expires) state must not be restored."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_purge_orphan_staff_password_requests"),
    ]

    operations = [
        migrations.RunPython(_backfill_expiry, _noop_reverse),
    ]
