from typing import Any

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class PublicTrigramExtension(TrigramExtension):
    """Installs pg_trgm in the public schema so gin_trgm_ops is available across

    all tenant schemas (Doc 02 §2, §5.2). Idempotent across multiple tenant schemas.
    """

    def database_forwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA public;")

    def database_backwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        pass


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("branches", "0001_initial"),
    ]

    operations = [
        PublicTrigramExtension(),
    ]
