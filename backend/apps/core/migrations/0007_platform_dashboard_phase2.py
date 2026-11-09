"""Phase 2 Platform Dashboard Models Migration.

- Adds Subscription.billing_cycle and Subscription.next_due
- Creates SubscriptionPayment table
- Creates TenantFeatureFlag table
- Creates DemoRequest table
- Creates PlatformSetting table
- Creates PlatformUserInvitation table
- Seeds default commercial & operational settings
"""

import uuid
from typing import Any

import django.db.models.deletion
import django.utils.timezone
from django.contrib.postgres.functions import RandomUUID
from django.db import migrations, models


def seed_default_settings(apps: Any, schema_editor: Any) -> None:
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    PlatformSetting = apps.get_model("core", "PlatformSetting")

    defaults = {
        "commercial_tiers": {
            "starter_price": "2999.00",
            "growth_price": "5999.00",
            "scale_price": "9999.00",
            "lifetime_single_price": "71999.00",
            "lifetime_multi_price": "143999.00",
            "annual_maintenance_pct": 15,
        },
        "founding_offer": {
            "slots_total": 10,
            "enabled": True,
        },
        "platform_toggles": {
            "new_signups_enabled": True,
            "maintenance_mode": False,
        },
    }

    for key, val in defaults.items():
        PlatformSetting.objects.update_or_create(
            key=key,
            defaults={"value": val},
        )


def noop_reverse(apps: Any, schema_editor: Any) -> None:
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_platform_dashboard_phase1_rebuild"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="billing_cycle",
            field=models.CharField(
                default="monthly",
                help_text="Billing cadence: monthly, annual, lifetime",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="next_due",
            field=models.DateField(
                blank=True,
                help_text="Next payment renewal due date",
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="SubscriptionPayment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=RandomUUID(),
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Settled amount in PKR",
                        max_digits=12,
                    ),
                ),
                (
                    "method",
                    models.CharField(
                        help_text="Payment method: Bank Transfer, Easypaisa, JazzCash",
                        max_length=50,
                    ),
                ),
                (
                    "reference",
                    models.CharField(
                        help_text="Bank transaction or gateway reference number",
                        max_length=100,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Settlement reason or operator notes",
                    ),
                ),
                (
                    "paid_date",
                    models.DateField(
                        default=django.utils.timezone.now,
                        help_text="Date funds were received",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="recorded_by_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_payments",
                        to="core.platformuser",
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        blank=True,
                        db_column="subscription_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payments",
                        to="core.subscription",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        db_column="tenant_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payments",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "subscription_payment",
                "indexes": [
                    models.Index(fields=["tenant"], name="idx_sub_payment_tenant"),
                    models.Index(fields=["subscription"], name="idx_sub_payment_sub"),
                    models.Index(
                        fields=["paid_date"], name="idx_sub_payment_paid_date"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="TenantFeatureFlag",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=RandomUUID(),
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "flag_key",
                    models.CharField(
                        help_text="Feature flag identifier: referral_partners, settlements, etc.",
                        max_length=100,
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this enterprise feature scope is unlocked",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        db_column="tenant_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_flags",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "tenant_feature_flag",
                "indexes": [
                    models.Index(fields=["tenant"], name="idx_tenant_feature_flag_t")
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["tenant", "flag_key"],
                        name="uq_tenant_feature_flag",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="DemoRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=RandomUUID(),
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "lab_name",
                    models.CharField(help_text="Facility display name", max_length=255),
                ),
                (
                    "contact_person",
                    models.CharField(
                        help_text="Primary director/doctor", max_length=255
                    ),
                ),
                (
                    "whatsapp",
                    models.CharField(
                        help_text="Direct mobile / WhatsApp", max_length=50
                    ),
                ),
                (
                    "message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Original inquiry text",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("contacted", "Contacted"),
                            ("demo_done", "Demo Done"),
                            ("converted", "Converted"),
                            ("lost", "Lost"),
                        ],
                        default="new",
                        help_text="Commercial lead qualification status",
                        max_length=50,
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Internal account notes",
                    ),
                ),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                (
                    "converted_tenant",
                    models.ForeignKey(
                        blank=True,
                        db_column="converted_tenant_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="demo_requests",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "demo_request",
                "indexes": [
                    models.Index(fields=["status"], name="idx_demo_req_status"),
                    models.Index(
                        fields=["requested_at"], name="idx_demo_req_requested_at"
                    ),
                    models.Index(
                        fields=["converted_tenant"], name="idx_demo_req_tenant"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PlatformSetting",
            fields=[
                (
                    "key",
                    models.CharField(max_length=100, primary_key=True, serialize=False),
                ),
                ("value", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="updated_by_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="core.platformuser",
                    ),
                ),
            ],
            options={
                "db_table": "platform_setting",
            },
        ),
        migrations.CreateModel(
            name="PlatformUserInvitation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=RandomUUID(),
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("role", models.CharField(default="support", max_length=50)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted", "Accepted"),
                            ("revoked", "Revoked"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="invited_by_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="core.platformuser",
                    ),
                ),
            ],
            options={
                "db_table": "platform_user_invitation",
            },
        ),
        migrations.RunPython(seed_default_settings, noop_reverse),
    ]
