"""Staff identity for staff CRUD and role gating.

Adds:
- ``StaffUser.display_name`` — the human-readable identity shown in the staff
  list, audit trail, approval queue, ledgers and report footers (D-B).
- ``StaffUser.created_by`` — the Owner account that created a staff member
  through Staff CRUD (NULL for provisioning-created Owners).
- A case-insensitive unique constraint on ``email``. The existing exact-match
  constraint remains; login already lowercases the submitted address, so this
  closes the ``Ali@`` / ``ali@`` duplicate hole without touching passwords,
  TOTP secrets or backup codes.

Existing rows get a deterministic display name derived from the email local
part when none is present. No password, TOTP secret or backup code is read or
rewritten by this migration.
"""

from typing import Any

from django.db import migrations, models
from django.db.models.functions import Lower


def _display_name_from_email(email: str) -> str:
    local = (email or "").split("@", 1)[0]
    cleaned = " ".join(
        part for part in local.replace("_", " ").replace(".", " ").split() if part
    )
    return cleaned.title()[:255]


def backfill_identity(apps: Any, schema_editor: Any) -> None:
    StaffUser = apps.get_model("accounts", "StaffUser")
    db_alias = schema_editor.connection.alias

    for staff in StaffUser.objects.using(db_alias).all().iterator():
        changed: list[str] = []
        lowered = (staff.email or "").strip().lower()
        if lowered and lowered != staff.email:
            staff.email = lowered
            changed.append("email")
        if not (staff.display_name or "").strip():
            staff.display_name = _display_name_from_email(lowered)
            changed.append("display_name")
        if changed:
            staff.save(using=db_alias, update_fields=changed)


def noop_reverse(apps: Any, schema_editor: Any) -> None:
    """Reversing the backfill would rewrite identity data; leave it intact."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_staffuser_password_is_temporary"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffuser",
            name="display_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Human-readable name shown in audit trails, approvals, "
                    "ledgers and report footers. Required for accounts created "
                    "through Staff CRUD."
                ),
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="staffuser",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                db_column="created_by_id",
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="created_staff",
                to="accounts.staffuser",
            ),
        ),
        migrations.RunPython(backfill_identity, noop_reverse),
        migrations.AddConstraint(
            model_name="staffuser",
            constraint=models.UniqueConstraint(
                Lower("email"), name="uq_staff_user_email_ci"
            ),
        ),
    ]
