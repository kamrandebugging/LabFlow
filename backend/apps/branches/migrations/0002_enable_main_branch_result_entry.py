"""Repair the provisioned result-entry flag on the main branch.

Provisioning used to seed every branch with ``result_entry_enabled=False``,
including the main testing branch. Labs could still enter results (the flag is
advisory in the accessioning flow), but the branch screen told operators the
opposite. Enable it on the main branch of tenant schemas that have no branch
with result entry enabled, leaving deliberately configured labs untouched.
"""

from django.db import migrations


def enable_main_branch_result_entry(apps, schema_editor):  # type: ignore[no-untyped-def]
    Branch = apps.get_model("branches", "Branch")
    if Branch.objects.filter(result_entry_enabled=True).exists():
        return
    Branch.objects.filter(code="HQ1").update(result_entry_enabled=True)


def noop(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Irreversible repair: leaving the flag on is harmless."""


class Migration(migrations.Migration):
    dependencies = [
        ("branches", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_main_branch_result_entry, noop),
    ]
