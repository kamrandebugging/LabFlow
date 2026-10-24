import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Branch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("code", models.CharField(max_length=3)),
                ("name", models.CharField(max_length=255)),
                ("address", models.TextField(blank=True, null=True)),
                ("phone", models.CharField(blank=True, max_length=32, null=True)),
                ("is_collection_centre", models.BooleanField(default=False)),
                ("result_entry_enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "branch",
            },
        ),
        migrations.AddConstraint(
            model_name="branch",
            constraint=models.UniqueConstraint(fields=("code",), name="uq_branch_code"),
        ),
        migrations.AddIndex(
            model_name="branch",
            index=models.Index(fields=["deleted_at"], name="idx_branch_deleted_at"),
        ),
    ]
