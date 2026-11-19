from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("samples", "0003_sample_recollected_from"),
    ]

    operations = [
        migrations.AddField(
            model_name="sample",
            name="collection_notes",
            field=models.TextField(blank=True, null=True),
        ),
    ]
