"""Master Dashboard Phase 1: tenant branch counter, platform reset tokens.

- ``tenant.branch_count`` is the denormalized active-branch counter that the
  platform surface reads instead of touching a tenant schema (Doc 04 TP-4).
- ``platform_audit.entity_id`` becomes nullable so a failed login for an
  unknown email can still be audited with an unresolvable subject.
- ``platform_password_reset_token`` stores only the argon2 hash (Doc 08 §4.5).
"""

import uuid
from typing import Any

import django.contrib.postgres.functions
import django.db.models.deletion
from django.db import migrations, models


def backfill_branch_count(apps: Any, schema_editor: Any) -> None:
    """Populate tenant.branch_count from each existing tenant schema.

    Schemas that do not exist yet (tests create them after migrating) are
    skipped: ``to_regclass`` returns NULL and the counter stays at its default.
    """
    Tenant = apps.get_model("core", "Tenant")
    connection = schema_editor.connection
    for tenant in Tenant.objects.exclude(schema_name="public").iterator():
        schema_name = tenant.schema_name
        # Defence in depth: never interpolate an unvalidated identifier.
        if not schema_name.startswith("tenant_") or not all(
            part.isalnum() or part == "_" for part in schema_name
        ):
            continue
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", [f'"{schema_name}".branch'])
            if cursor.fetchone()[0] is None:
                continue
            cursor.execute(
                f'SELECT COUNT(*) FROM "{schema_name}".branch WHERE deleted_at IS NULL'
            )
            count = cursor.fetchone()[0]
        Tenant.objects.filter(pk=tenant.pk).update(branch_count=count)


def noop_reverse(apps: Any, schema_editor: Any) -> None:
    """Counter backfill is not reversible; the column drop reverts the schema."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_platform_audit_append_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="branch_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Active (non-closed) branch counter mirrored from the tenant "
                    "schema by BranchService (Doc 04 TP-4)."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="platformaudit",
            name="entity_id",
            field=models.UUIDField(
                blank=True,
                help_text=(
                    "Polymorphic target entity UUID (no FK); NULL when the subject "
                    "could not be resolved, e.g. a failed login for an unknown email"
                ),
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="PlatformPasswordResetToken",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=django.contrib.postgres.functions.RandomUUID(),
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "token_hash",
                    models.CharField(help_text="argon2 token hash", max_length=255),
                ),
                ("expires_at", models.DateTimeField(help_text="Hard expiry timestamp")),
                (
                    "used_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Consumption timestamp; NULL while still usable",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "platform_user",
                    models.ForeignKey(
                        db_column="platform_user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_reset_tokens",
                        to="core.platformuser",
                    ),
                ),
            ],
            options={
                "db_table": "platform_password_reset_token",
                "indexes": [
                    models.Index(
                        fields=["platform_user", "used_at"],
                        name="idx_platform_reset_user_used",
                    )
                ],
            },
        ),
        migrations.RunPython(backfill_branch_count, noop_reverse),
    ]
