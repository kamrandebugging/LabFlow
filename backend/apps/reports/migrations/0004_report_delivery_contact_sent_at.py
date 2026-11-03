# LAB-32 (KAN-157): report_delivery gains the target patient_contact
# (backs the Doc 03 §6.7 channel+contact idempotency rule), a sent_at
# timestamp (delivery latency metrics), and a partial UNIQUE
# (report, channel, contact) WHERE status='PENDING' so concurrent deliver
# calls can never create two live PENDING intents (§10).
#
# Doc 02 §5.7 note: the v1.3 column list did not carry contact_id/sent_at;
# they are added here as the schema evolution required by the §6.7 deliver
# contract. Table is pre-production; no data backfill needed.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0003_report_generation_status"),
        ("patients", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportdelivery",
            name="contact",
            field=models.ForeignKey(
                db_column="contact_id",
                db_index=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="report_deliveries",
                to="patients.patientcontact",
            ),
        ),
        migrations.AddField(
            model_name="reportdelivery",
            name="sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="reportdelivery",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="PENDING"),
                fields=("report", "channel", "contact"),
                name="uq_report_delivery_pending_report_channel_contact",
            ),
        ),
    ]
