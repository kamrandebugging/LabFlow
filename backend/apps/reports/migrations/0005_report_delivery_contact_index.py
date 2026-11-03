# LAB-32 (KAN-157) follow-up: add a dedicated index on
# report_delivery.contact_id. The LAB-7 Definition of Done test requires an
# index on every FK column across the 22 LAB-7 models; contact_id was added
# without one (db_index=False) and failed CI check 8.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0004_report_delivery_contact_sent_at"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="reportdelivery",
            index=models.Index(
                fields=["contact"],
                name="idx_report_delivery_contact_id",
            ),
        ),
    ]
