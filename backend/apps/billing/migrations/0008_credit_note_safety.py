import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0007_day_close"),
        ("accounts", "0012_backfill_temp_password_expiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditnote",
            name="method",
            field=models.TextField(
                choices=[
                    ("cash", "Cash"),
                    ("card", "Card"),
                    ("bank_transfer", "Bank Transfer"),
                    ("easypaisa", "Easypaisa"),
                    ("jazzcash", "JazzCash"),
                    ("other", "Other"),
                ],
                db_default="cash",
                default="cash",
            ),
        ),
        migrations.AddField(
            model_name="creditnote",
            name="reversed_methods",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="creditnote",
            name="idempotency_key",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="creditnote",
            name="payload_sha256",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="creditnote",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="creditnote",
            name="void_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="creditnote",
            name="voided_by",
            field=models.ForeignKey(
                blank=True,
                db_column="voided_by_id",
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="credit_notes_voided",
                to="accounts.staffuser",
            ),
        ),
        migrations.AddConstraint(
            model_name="creditnote",
            constraint=models.UniqueConstraint(
                fields=("invoice",), name="uq_credit_note_invoice"
            ),
        ),
        migrations.AddConstraint(
            model_name="creditnote",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("idempotency_key",),
                name="uq_credit_note_idempotency_key",
            ),
        ),
    ]
