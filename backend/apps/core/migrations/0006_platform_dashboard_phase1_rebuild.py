"""Phase 1 Platform Dashboard Rebuild Migration.

- Adds Plan.max_staff
- Adds Tenant extended metadata (city, province, owner_name, owner_email, owner_phone,
  staff_seats_limit, staff_count, temp_password, temp_password_expires_at, enabled_roles)
- Seeds official platform plans (Starter, Growth, Scale, Lifetime Single, Lifetime Multi)
- Retires demo "Standard Lab PKR 10000" plan
"""

from decimal import Decimal
from typing import Any

import django.contrib.postgres.fields
from django.db import migrations, models


def seed_real_plans_and_retire_demo(apps: Any, schema_editor: Any) -> None:
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    Plan = apps.get_model("core", "Plan")

    # 1. Retire any demo Standard Lab plans
    Plan.objects.filter(name__icontains="Standard Lab").update(is_active=False)

    # 2. Seed official plans per prompt specifications:
    # Starter 2,999 / 1 branch / 5 staff
    # Growth 5,999 / 3 branches / unlimited staff
    # Scale 9,999 / unlimited / unlimited
    # Lifetime Single 71,999 / 1 branch / 5 staff
    # Lifetime Multi 143,999 / unlimited / unlimited
    official_plans = [
        {
            "name": "Starter",
            "price": Decimal("2999.00"),
            "max_branches": 1,
            "max_staff": 5,
            "is_active": True,
        },
        {
            "name": "Growth",
            "price": Decimal("5999.00"),
            "max_branches": 3,
            "max_staff": None,
            "is_active": True,
        },
        {
            "name": "Scale",
            "price": Decimal("9999.00"),
            "max_branches": None,
            "max_staff": None,
            "is_active": True,
        },
        {
            "name": "Lifetime (Single Branch)",
            "price": Decimal("71999.00"),
            "max_branches": 1,
            "max_staff": 5,
            "is_active": True,
        },
        {
            "name": "Lifetime (Multi-Branch)",
            "price": Decimal("143999.00"),
            "max_branches": None,
            "max_staff": None,
            "is_active": True,
        },
    ]

    for p in official_plans:
        existing = Plan.objects.filter(name=p["name"]).first()
        if existing:
            existing.price = p["price"]
            existing.max_branches = p["max_branches"]
            existing.max_staff = p["max_staff"]
            existing.is_active = p["is_active"]
            existing.save()
        else:
            Plan.objects.create(**p)


def noop_reverse(apps: Any, schema_editor: Any) -> None:
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_master_dashboard_phase1"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="max_staff",
            field=models.IntegerField(
                blank=True,
                help_text="Maximum staff permitted; NULL denotes unlimited",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="city",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Primary facility city",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="province",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Primary facility province/region",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="owner_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Primary administrator / medical director name",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="owner_email",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Primary administrator email address",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="owner_phone",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Primary contact phone / WhatsApp",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="staff_seats_limit",
            field=models.IntegerField(
                blank=True,
                help_text="Maximum allowed staff seats; NULL denotes unlimited",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="staff_count",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Current staff count",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="temp_password",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Initial temporary credential issued during provisioning",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="temp_password_expires_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Expiry timestamp for temporary credential (24h)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="enabled_roles",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=50),
                blank=True,
                default=list,
                help_text="List of roles enabled during provisioning",
                size=None,
            ),
        ),
        migrations.RunPython(seed_real_plans_and_retire_demo, noop_reverse),
    ]
