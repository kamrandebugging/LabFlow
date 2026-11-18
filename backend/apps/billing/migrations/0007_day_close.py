import uuid

import django.db.models.deletion
import django.db.models.functions.datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_backfill_temp_password_expiry"),
        ("billing", "0006_credit_note"),
        ("branches", "0002_enable_main_branch_result_entry"),
    ]

    operations = [
        migrations.CreateModel(
            name="DayClose",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=models.Func(function="gen_random_uuid"),
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("business_date", models.DateField()),
                ("method_totals", models.JSONField()),
                ("total_invoices", models.PositiveIntegerField(default=0)),
                (
                    "total_discount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "total_credit_notes",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "expected_cash",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                (
                    "counted_cash",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                ("difference", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "difference_note",
                    models.TextField(blank=True, null=True),
                ),
                (
                    "closed_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_default=django.db.models.functions.datetime.Now(),
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        db_column="branch_id",
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="day_closes",
                        to="branches.branch",
                    ),
                ),
                (
                    "closed_by",
                    models.ForeignKey(
                        db_column="closed_by",
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="day_closes",
                        to="accounts.staffuser",
                    ),
                ),
            ],
            options={
                "db_table": "billing_day_close",
                "ordering": ["-business_date"],
            },
        ),
        migrations.AddConstraint(
            model_name="dayclose",
            constraint=models.UniqueConstraint(
                fields=("branch", "business_date"),
                name="uq_day_close_branch_date",
            ),
        ),
        migrations.AddIndex(
            model_name="dayclose",
            index=models.Index(fields=["branch"], name="idx_day_close_branch_id"),
        ),
    ]
