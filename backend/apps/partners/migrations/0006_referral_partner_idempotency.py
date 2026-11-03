# LAB-39 (KAN-164): idempotency key for referral-partner creation.
#
# POST /referral-partners requires an Idempotency-Key header (same contract
# as invoices/payments). The partial UNIQUE index makes replays safe:
# same key + same payload -> 200 with the original; same key + different
# payload -> 409 idempotency_key_reused.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0005_share_ledger_entry_append_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralpartner",
            name="idempotency_key",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="referralpartner",
            index=models.Index(
                condition=models.Q(idempotency_key__isnull=False),
                fields=["idempotency_key"],
                name="uq_referral_partner_idempotency_key",
            ),
        ),
    ]
