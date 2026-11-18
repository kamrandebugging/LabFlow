import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_backfill_temp_password_expiry"),
        ("billing", "0005_payment_refund_reason"),
    ]

    operations = [
        migrations.CreateModel(
            name="CreditNoteSequence",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
            options={
                "db_table": "billing_credit_note_sequence",
            },
        ),
        migrations.CreateModel(
            name="CreditNote",
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
                ("number", models.TextField(unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("reason", models.TextField()),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invoice",
                    models.ForeignKey(
                        db_column="invoice_id",
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="credit_notes",
                        to="billing.invoice",
                    ),
                ),
                (
                    "issued_by",
                    models.ForeignKey(
                        db_column="issued_by_id",
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="credit_notes_issued",
                        to="accounts.staffuser",
                    ),
                ),
            ],
            options={
                "db_table": "billing_credit_note",
                "ordering": ["issued_at", "number"],
            },
        ),
        migrations.AddConstraint(
            model_name="creditnote",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gt", 0)),
                name="chk_credit_note_amount_pos",
            ),
        ),
        migrations.AddIndex(
            model_name="creditnote",
            index=models.Index(fields=["invoice"], name="idx_credit_note_invoice_id"),
        ),
    ]
