import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0002_initial"),
        ("partners", "0007_drop_settlement_line_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="referral_partner",
            field=models.ForeignKey(
                blank=True,
                db_column="referral_partner_id",
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="patients",
                to="partners.referralpartner",
            ),
        ),
        migrations.AddIndex(
            model_name="patient",
            index=models.Index(
                fields=["referral_partner"],
                name="idx_patient_referral_partner_id",
            ),
        ),
    ]
