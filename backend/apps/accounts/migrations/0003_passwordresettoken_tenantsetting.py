import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_staffbranch_loginevent"),
    ]

    operations = [
        migrations.CreateModel(
            name="PasswordResetToken",
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
                ("token_hash", models.CharField(max_length=255)),
                (
                    "purpose",
                    models.CharField(
                        choices=[
                            ("password_reset", "Password Reset"),
                            ("email_verification", "Email Verification"),
                            ("activation", "Activation"),
                        ],
                        default="password_reset",
                        max_length=32,
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "staff_user",
                    models.ForeignKey(
                        db_column="staff_user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_reset_tokens",
                        to="accounts.staffuser",
                    ),
                ),
            ],
            options={
                "db_table": "password_reset_token",
            },
        ),
        migrations.CreateModel(
            name="TenantSetting",
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
                ("key", models.CharField(max_length=255)),
                ("value", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="updated_by",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tenant_settings",
                        to="accounts.staffuser",
                    ),
                ),
            ],
            options={
                "db_table": "tenant_setting",
            },
        ),
        migrations.AddIndex(
            model_name="tenantsetting",
            index=models.Index(
                fields=["updated_by"], name="idx_tenant_setting_updated_by_id"
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantsetting",
            constraint=models.UniqueConstraint(
                fields=("key",), name="uq_tenant_setting_key"
            ),
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(
                fields=["staff_user"],
                name="idx_password_reset_token_staff_user_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="passwordresettoken",
            constraint=models.UniqueConstraint(
                fields=("token_hash",),
                name="uq_password_reset_token_token_hash",
            ),
        ),
        migrations.AddConstraint(
            model_name="passwordresettoken",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    purpose__in=[
                        "password_reset",
                        "email_verification",
                        "activation",
                    ]
                ),
                name="chk_password_reset_token_purpose",
            ),
        ),
        migrations.AddConstraint(
            model_name="passwordresettoken",
            constraint=models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="chk_password_reset_token_expires_gt_created",
            ),
        ),
    ]
