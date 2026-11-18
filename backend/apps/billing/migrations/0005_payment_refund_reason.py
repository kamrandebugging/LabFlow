from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0004_lab19_payment_payload_sha256"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="refund_reason",
            field=models.TextField(blank=True, null=True),
        ),
    ]
