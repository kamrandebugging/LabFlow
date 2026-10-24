import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("branches", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LoginEvent",
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
                ("email_attempted", models.CharField(max_length=255)),
                ("success", models.BooleanField()),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "staff_user",
                    models.ForeignKey(
                        blank=True,
                        db_column="staff_user_id",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="login_events",
                        to="accounts.staffuser",
                    ),
                ),
            ],
            options={
                "db_table": "login_event",
                "indexes": [
                    models.Index(
                        fields=["staff_user"],
                        name="idx_login_event_staff_user_id",
                    ),
                    models.Index(
                        fields=["created_at"],
                        name="idx_login_event_created_at",
                    ),
                    models.Index(
                        fields=["email_attempted", "created_at"],
                        name="idx_login_event_email_created",
                    ),
                    models.Index(
                        fields=["ip", "created_at"],
                        name="idx_login_event_ip_created",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="StaffBranch",
            fields=[
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "staff_user_id",
                        "branch_id",
                        blank=True,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("is_primary", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "branch",
                    models.ForeignKey(
                        db_column="branch_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_branches",
                        to="branches.branch",
                    ),
                ),
                (
                    "staff_user",
                    models.ForeignKey(
                        db_column="staff_user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_branches",
                        to="accounts.staffuser",
                    ),
                ),
            ],
            options={
                "db_table": "staff_branch",
                "indexes": [
                    models.Index(
                        fields=["staff_user"],
                        name="idx_staff_branch_staff_user_id",
                    ),
                    models.Index(
                        fields=["branch"],
                        name="idx_staff_branch_branch_id",
                    ),
                ],
            },
        ),
    ]
