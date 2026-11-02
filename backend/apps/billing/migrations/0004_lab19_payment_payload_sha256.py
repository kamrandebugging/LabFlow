# Generated for LAB-19 (KAN-130) — payload fingerprint for payment idempotency (BL-4 pattern).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_lab18_payload_sha256"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="payload_sha256",
            field=models.TextField(blank=True, null=True),
        ),
    ]
