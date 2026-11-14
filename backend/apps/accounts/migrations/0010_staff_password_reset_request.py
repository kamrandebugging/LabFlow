import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_staffuser_temp_password_expires_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffPasswordResetRequest",
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
                ("email", models.EmailField(max_length=255)),
                (
                    "display_name",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("resolved", "Resolved")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_by", models.UUIDField(blank=True, null=True)),
            ],
            options={
                "db_table": "staff_password_reset_request",
                "indexes": [
                    models.Index(
                        fields=["status", "created_at"],
                        name="idx_staff_pwreset_status",
                    ),
                    models.Index(fields=["email"], name="idx_staff_pwreset_email"),
                ],
            },
        ),
    ]
