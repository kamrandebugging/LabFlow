from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("samples", "0004_sample_collection_notes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE sample_event
                    ADD CONSTRAINT chk_sample_event_event
                    CHECK (event IN ('COLLECTED', 'RECEIVED', 'IN_PROCESS', 'REJECTED', 'TRANSFERRED_IN', 'TRANSFERRED_OUT', 'TRANSFER_CANCELLED', 'TRANSFER_LOST', 'READY', 'CANCELLED'))
                    NOT VALID;
                    ALTER TABLE sample_event VALIDATE CONSTRAINT chk_sample_event_event;
                    """,
                    reverse_sql="ALTER TABLE sample_event DROP CONSTRAINT IF EXISTS chk_sample_event_event;",
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="sampleevent",
                    constraint=models.CheckConstraint(
                        condition=models.Q(
                            event__in=[
                                "COLLECTED",
                                "RECEIVED",
                                "IN_PROCESS",
                                "REJECTED",
                                "TRANSFERRED_IN",
                                "TRANSFERRED_OUT",
                                "TRANSFER_CANCELLED",
                                "TRANSFER_LOST",
                                "READY",
                                "CANCELLED",
                            ]
                        ),
                        name="chk_sample_event_event",
                    ),
                ),
            ],
        ),
    ]
