"""Align the tenant temp-password field state with the model.

Migration 0009 added ``temp_password_hash`` and changed the ``temp_password``
help text in the model, but did not record that help-text change, leaving the
migration state out of sync with ``apps.core.models.Tenant`` (Doc 09 §7.5).
This migration records the model change; it is state-only (no column SQL).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_tenant_temp_password_hash"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="temp_password",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Deprecated plaintext slot; always empty. The one-time "
                    "credential is returned at creation only and never stored "
                    "in plaintext."
                ),
                max_length=64,
            ),
        ),
    ]
