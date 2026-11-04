# LAB-41 (KAN-260): drop the UNIQUE on settlement_line.share_ledger_entry.
#
# Doc 05 §7.6 ST-19 requires re-draft after cancellation to insert a new
# settlement that "picks up the same entries" with new lines. A UNIQUE on
# share_ledger_entry makes that impossible. "One live line per entry" is
# enforced in settlement_service.select_draft_entries (only pending entries
# are selected) plus the settlement partial unique uq_settlement_partner_id_period
# (ST-7 idempotency).

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0006_referral_partner_idempotency"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="settlementline",
            name="uq_settlement_line_share_ledger_entry_id",
        ),
    ]
