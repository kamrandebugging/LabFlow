import uuid

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("branches", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffUser",
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
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Lab Owner"),
                            ("manager", "Branch Manager"),
                            ("reception", "Receptionist / Collection Staff"),
                            ("technician", "Lab Technician"),
                            ("pathologist", "Pathologist"),
                        ],
                        max_length=50,
                    ),
                ),
                ("email", models.EmailField(max_length=255)),
                ("password_hash", models.CharField(max_length=255)),
                (
                    "totp_secret_encrypted",
                    models.TextField(blank=True, null=True),
                ),
                (
                    "totp_backup_codes_hash",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.TextField(),
                        blank=True,
                        null=True,
                        size=None,
                    ),
                ),
                ("totp_enabled", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        db_column="branch_id",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="staff_users",
                        to="branches.branch",
                    ),
                ),
            ],
            options={
                "db_table": "staff_user",
            },
        ),
        migrations.AddConstraint(
            model_name="staffuser",
            constraint=models.UniqueConstraint(
                fields=("email",), name="uq_staff_user_email"
            ),
        ),
        migrations.AddIndex(
            model_name="staffuser",
            index=models.Index(fields=["branch"], name="idx_staff_user_branch_id"),
        ),
    ]
