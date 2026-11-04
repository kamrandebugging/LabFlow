# LAB-45 (KAN-264): report_delivery gains the idempotency_key column shared
# with the matching webhook_delivery row (Doc 06 §5.1). The n8n callback
# carries it and §5.4 check 5 looks the row up by it. Partial UNIQUE
# (IK-3): one key names one logical delivery.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0005_report_delivery_contact_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportdelivery",
            name="idempotency_key",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="reportdelivery",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("idempotency_key",),
                name="uq_report_delivery_idempotency_key",
            ),
        ),
    ]
