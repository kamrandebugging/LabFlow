import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("samples", "0002_accessioncounter"),
    ]

    operations = [
        migrations.AddField(
            model_name="sample",
            name="recollected_from",
            field=models.ForeignKey(
                blank=True,
                db_column="recollected_from_id",
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="recollections",
                to="samples.sample",
            ),
        ),
        migrations.AddIndex(
            model_name="sample",
            index=models.Index(
                fields=["recollected_from"], name="idx_sample_recollected_from"
            ),
        ),
    ]
