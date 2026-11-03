# LAB-38 (KAN-163): DataExport model for tenant data portability (Doc 04 §4.3).
#
# Tracks a Lab Owner's export request: status lifecycle, bundle storage key,
# signed download URL (7-day validity), and error text on failure.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_audit_log_append_only"),
    ]

    operations = [
        migrations.CreateModel(
            name="DataExport",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "status",
                    models.TextField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("complete", "Complete"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                    ),
                ),
                ("bundle_key", models.TextField(blank=True, null=True)),
                ("download_url", models.TextField(blank=True, null=True)),
                ("download_expires_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        db_column="requested_by",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="data_exports",
                        to="accounts.staffuser",
                    ),
                ),
            ],
            options={
                "db_table": "data_export",
                "indexes": [
                    models.Index(
                        fields=["requested_by"],
                        name="idx_data_export_requested_by_id",
                    ),
                    models.Index(fields=["status"], name="idx_data_export_status"),
                    models.Index(
                        fields=["created_at"], name="idx_data_export_created_at"
                    ),
                ],
            },
        ),
    ]
