import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_passwordresettoken_tenantsetting"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
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
                ("actor_id", models.UUIDField(blank=True, null=True)),
                ("action", models.CharField(max_length=255)),
                ("entity_type", models.CharField(max_length=255)),
                ("entity_id", models.UUIDField()),
                ("before_jsonb", models.JSONField(blank=True, null=True)),
                ("after_jsonb", models.JSONField(blank=True, null=True)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, null=True)),
                ("at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "audit_log",
                "indexes": [
                    models.Index(fields=["at"], name="idx_audit_log_at"),
                    models.Index(
                        fields=["entity_type", "entity_id"],
                        name="idx_audit_log_entity_type_entity_id",
                    ),
                    models.Index(fields=["actor_id"], name="idx_audit_log_actor_id"),
                ],
            },
        ),
    ]
