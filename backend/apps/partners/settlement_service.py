"""Monthly settlement generation service (LAB-41 / KAN-160...KAN-165 follow-up).

Doc 05 §7.2 (ST-1–ST-8): the monthly draft.
Doc 05 §12.5 (CF-1–CF-4): late-arriving entries.
Doc 05 §7.4 (ST-9–ST-12): approval + finalize task.

All money is Decimal. No business logic lives in views — this module owns it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# Template version recorded at finalize (Doc 05 §8.4, A-18 interim).
STATEMENT_TEMPLATE_VERSION = "A-18-interim"


def previous_period(today: date | None = None) -> str:
    """Return the previous calendar month as 'YYYY-MM' (the settlement period).

    Generation runs on the 1st; the period being settled is the month that
    just ended.
    """
    today = today or timezone.now().date()
    year, month = today.year, today.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _pending_entry_ids(partner_id: uuid.UUID) -> set[uuid.UUID]:
    """Return IDs of entries whose derived status is 'pending' (Doc 05 §6.7).

    Pending = no settlement_line on a live (non-CANCELLED) settlement.
    """
    from apps.partners.models import SettlementLine, ShareLedgerEntry

    live_line_entry_ids = set(
        SettlementLine.objects.filter(
            share_ledger_entry__referral_partner_id=partner_id,
        )
        .exclude(settlement__status="CANCELLED")
        .values_list("share_ledger_entry_id", flat=True)
    )
    all_ids = set(
        ShareLedgerEntry.objects.filter(referral_partner_id=partner_id).values_list(
            "id", flat=True
        )
    )
    return all_ids - live_line_entry_ids


def select_draft_entries(partner_id: uuid.UUID, target_period: str) -> list[Any]:
    """Select ledger entries for one partner's draft (Doc 05 §7.2 ST-3, §12.5 CF-4).

    - Entries with derived status 'pending' and stored period == target_period.
    - Plus still-pending entries from earlier periods whose period settlement
      is closed (APPROVED/SENT/PAID) or has no settlement at all.
    - Excludes entries from earlier periods whose period settlement is still
      DRAFT (CF-2: they join only via cancel + re-draft).
    """
    from apps.partners.models import Settlement, ShareLedgerEntry

    pending_ids = _pending_entry_ids(partner_id)
    if not pending_ids:
        return []

    entries = list(
        ShareLedgerEntry.objects.filter(id__in=pending_ids).order_by("created_at", "id")
    )
    # Map period -> live settlement status for this partner.
    settlements = Settlement.objects.filter(referral_partner_id=partner_id).exclude(
        status="CANCELLED"
    )
    period_status: dict[str, str] = {}
    for s in settlements:
        # A partner has at most one live settlement per period (partial unique).
        period_status.setdefault(s.period, s.status)

    selected: list[Any] = []
    for e in entries:
        if e.period == target_period:
            selected.append(e)
        elif e.period < target_period:
            st = period_status.get(e.period)
            if st is None or st in ("APPROVED", "SENT", "PAID"):
                # No settlement yet, or the period is closed: late entry
                # joins the current draft (CF-3, CF-4).
                selected.append(e)
            # else: period settlement still DRAFT -> stays pending (CF-2).
        # Entries with period > target_period are future-dated; leave pending.
    return selected


def draft_partner_settlement(
    partner_id: uuid.UUID, target_period: str
) -> dict[str, Any]:
    """Draft one partner's settlement for the period (Doc 05 §7.2 ST-4–ST-7).

    Returns a result dict: status drafted|already_drafted|no_entries.
    One transaction per partner (ST-4). Idempotent via the partial unique
    index (ST-7): a re-run that hits the index is a no-op.
    """
    from apps.partners.models import Settlement, SettlementLine

    entries = select_draft_entries(partner_id, target_period)
    if not entries:
        # ST-5: no empty settlements.
        return {"status": "no_entries", "partner_id": str(partner_id)}

    total = sum((e.amount for e in entries), Decimal("0.00"))

    try:
        with transaction.atomic():
            settlement = Settlement.objects.create(
                referral_partner_id=partner_id,
                period=target_period,
                status=Settlement.Status.DRAFT,
                total=total,
            )
            SettlementLine.objects.bulk_create(
                [
                    SettlementLine(
                        settlement_id=settlement.id,
                        share_ledger_entry_id=e.id,
                        amount=e.amount,
                    )
                    for e in entries
                ]
            )
    except IntegrityError:
        # ST-7: partial unique index refused a second live row — already drafted.
        logger.info(
            "settlement draft: partner %s period %s already drafted — no-op",
            partner_id,
            target_period,
        )
        return {"status": "already_drafted", "partner_id": str(partner_id)}

    logger.info(
        "settlement draft: partner %s period %s drafted with %d lines, total %s",
        partner_id,
        target_period,
        len(entries),
        total,
    )
    return {
        "status": "drafted",
        "partner_id": str(partner_id),
        "settlement_id": str(settlement.id),
        "lines": len(entries),
        "total": str(total),
    }


def settlement_period_totals(settlement_id: uuid.UUID) -> dict[str, Decimal]:
    """Subtotals per entry period for multi-period statements (Doc 05 §8.2).

    Only used when the settlement holds lines from more than one period.
    """
    from apps.partners.models import SettlementLine

    rows = (
        SettlementLine.objects.filter(settlement_id=settlement_id)
        .values("share_ledger_entry__period")
        .annotate(subtotal=Sum("amount"))
        .order_by("share_ledger_entry__period")
    )
    return {r["share_ledger_entry__period"]: r["subtotal"] for r in rows}


def build_statement_context(
    settlement_id: uuid.UUID,
) -> dict[str, Any]:
    """Build the template context for a settlement statement (Doc 05 §8.2)."""
    from apps.partners.models import Settlement, SettlementLine

    settlement = Settlement.objects.select_related("referral_partner").get(
        id=settlement_id
    )
    partner = settlement.referral_partner
    lines = list(
        SettlementLine.objects.filter(settlement_id=settlement_id)
        .select_related("share_ledger_entry__payment")
        .order_by("share_ledger_entry__created_at", "id")
    )

    # Period label: "September 2026" for "2026-09".
    year, month = settlement.period.split("-")
    month_names = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    period_label = f"{month_names[int(month)]} {year}"

    line_rows = []
    for line in lines:
        entry = line.share_ledger_entry
        payment = entry.payment
        invoice_ref = str(payment.invoice_id) if payment else ""
        is_reversal = line.amount < 0
        line_rows.append(
            {
                "payment_date": payment.created_at.date().isoformat()
                if payment and payment.created_at
                else "",
                "invoice_reference": invoice_ref,
                "basis_amount": f"{entry.basis_amount:.2f}",
                "percent_applied": f"{entry.percent_applied:.2f}",
                "amount": f"{line.amount:.2f}",
                "is_reversal": is_reversal,
                "label": "Refund reversal" if is_reversal else "",
                "period": entry.period,
            }
        )

    periods: list[str] = sorted({str(r["period"]) for r in line_rows})
    subtotals = settlement_period_totals(settlement_id) if len(periods) > 1 else {}

    return {
        "statement_id": str(settlement.id),
        "period": settlement.period,
        "period_label": period_label,
        "currency": "PKR",
        "partner_name": partner.name,
        "partner_organisation": partner.organisation or "",
        "generated_date": timezone.now().date().isoformat(),
        "lines": line_rows,
        "subtotals": [
            {"period": p, "subtotal": f"{subtotals[p]:.2f}"} for p in sorted(subtotals)
        ],
        "total": f"{settlement.total:.2f}",
        "is_negative": settlement.total < 0,
        "template_version": STATEMENT_TEMPLATE_VERSION,
    }
