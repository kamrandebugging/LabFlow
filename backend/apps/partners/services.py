"""Business logic for the referral-partner registry (Doc 05 §5.1–§5.4, §10,
§12.5; KAN-164 / LAB-39).

Thin views call into these services. All state changes run inside a single
transaction that also writes the audit row (RP-6). Money stays Decimal.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import AuditLog, StaffUser
from apps.branches.models import Branch
from apps.partners.models import (
    ReferralPartner,
    RevenueShareRule,
    Settlement,
    SettlementLine,
    ShareLedgerEntry,
)

KARACHI = ZoneInfo("Asia/Karachi")


class PartnerError(Exception):
    """Service error carrying an API error code and HTTP status."""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


def _today() -> date:
    return timezone.now().astimezone(KARACHI).date()


def _audit(
    actor: StaffUser,
    action: str,
    entity_type: str,
    entity_id: UUID,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    ip: str = "",
) -> None:
    AuditLog.objects.create(
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_jsonb=before,
        after_jsonb=after,
        ip=ip or None,
    )


def _partner_snapshot(partner: ReferralPartner) -> dict[str, Any]:
    return {
        "name": partner.name,
        "organisation": partner.organisation,
        "phone": partner.phone,
        "email": partner.email,
        "is_active": partner.is_active,
        "deleted_at": partner.deleted_at.isoformat() if partner.deleted_at else None,
    }


def _rule_snapshot(rule: RevenueShareRule) -> dict[str, Any]:
    return {
        "referral_partner_id": str(rule.referral_partner_id),
        "branch_id": str(rule.branch_id) if rule.branch_id else None,
        "test_category": rule.test_category,
        "percent": f"{rule.percent:.2f}",
        "effective_from": rule.effective_from.isoformat(),
        "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
    }


def _payload_matches(partner: ReferralPartner, payload: dict[str, Any]) -> bool:
    current = _partner_snapshot(partner)
    for key in ("name", "organisation", "phone", "email", "is_active"):
        if current.get(key) != payload.get(key):
            return False
    return True


class PartnerService:
    """Referral-partner CRUD (Doc 05 §5.1, RP-1–RP-6). Owner only."""

    @staticmethod
    def _live() -> Any:
        return ReferralPartner.objects.filter(deleted_at__isnull=True)

    @staticmethod
    def get_partner(partner_id: UUID) -> ReferralPartner:
        try:
            return PartnerService._live().get(id=partner_id)
        except ReferralPartner.DoesNotExist as exc:
            raise PartnerError(
                "not_found",
                "Referral partner not found.",
                status.HTTP_404_NOT_FOUND,
            ) from exc

    @staticmethod
    def list_partners() -> Any:
        return PartnerService._live().order_by("name", "created_at")

    @staticmethod
    @transaction.atomic
    def create_partner(
        actor: StaffUser,
        payload: dict[str, Any],
        idempotency_key: str,
        ip: str = "",
    ) -> tuple[ReferralPartner, bool]:
        """Returns (partner, created). Replays return the original (created=False)."""
        existing = ReferralPartner.objects.filter(
            idempotency_key=idempotency_key, deleted_at__isnull=True
        ).first()
        if existing is not None:
            if _payload_matches(existing, payload):
                return existing, False
            raise PartnerError(
                "idempotency_key_reused",
                "Idempotency-Key was already used with a different payload.",
                status.HTTP_409_CONFLICT,
            )
        try:
            partner = ReferralPartner.objects.create(
                name=payload["name"],
                organisation=payload.get("organisation"),
                phone=payload.get("phone"),
                email=payload.get("email"),
                is_active=payload.get("is_active", True),
                idempotency_key=idempotency_key,
            )
        except IntegrityError as exc:
            # Lost a race with a concurrent insert carrying the same key.
            existing = ReferralPartner.objects.filter(
                idempotency_key=idempotency_key, deleted_at__isnull=True
            ).first()
            if existing is not None and _payload_matches(existing, payload):
                return existing, False
            raise PartnerError(
                "idempotency_key_reused",
                "Idempotency-Key was already used with a different payload.",
                status.HTTP_409_CONFLICT,
            ) from exc
        _audit(
            actor,
            "partner.created",
            "referral_partner",
            partner.id,
            None,
            _partner_snapshot(partner),
            ip,
        )
        return partner, True

    @staticmethod
    @transaction.atomic
    def update_partner(
        actor: StaffUser,
        partner_id: UUID,
        payload: dict[str, Any],
        ip: str = "",
    ) -> ReferralPartner:
        partner = PartnerService.get_partner(partner_id)
        before = _partner_snapshot(partner)
        for field in ("name", "organisation", "phone", "email", "is_active"):
            if field in payload:
                setattr(partner, field, payload[field])
        partner.save(
            update_fields=[
                "name",
                "organisation",
                "phone",
                "email",
                "is_active",
                "updated_at",
            ]
        )
        _audit(
            actor,
            "partner.updated",
            "referral_partner",
            partner.id,
            before,
            _partner_snapshot(partner),
            ip,
        )
        return partner

    @staticmethod
    @transaction.atomic
    def delete_partner(
        actor: StaffUser, partner_id: UUID, ip: str = ""
    ) -> ReferralPartner:
        """Soft delete. Refused while any ledger row points at the partner (RP-5)."""
        partner = PartnerService.get_partner(partner_id)
        if ShareLedgerEntry.objects.filter(referral_partner_id=partner.id).exists():
            raise PartnerError(
                "partner_has_ledger_entries",
                "Partner has ledger entries and cannot be deleted; "
                "deactivate it instead.",
                status.HTTP_409_CONFLICT,
            )
        before = _partner_snapshot(partner)
        partner.deleted_at = timezone.now()
        partner.save(update_fields=["deleted_at", "updated_at"])
        _audit(
            actor,
            "partner.deleted",
            "referral_partner",
            partner.id,
            before,
            _partner_snapshot(partner),
            ip,
        )
        return partner


def _bucket_rules(
    partner_id: UUID,
    branch_id: UUID | None,
    test_category: str | None,
    exclude_id: UUID | None = None,
) -> Any:
    """All rules in one specificity bucket (RR-6). NULL counts as a value."""
    qs = RevenueShareRule.objects.filter(
        referral_partner_id=partner_id,
        test_category=test_category,
    )
    if branch_id is None:
        qs = qs.filter(branch__isnull=True)
    else:
        qs = qs.filter(branch_id=branch_id)
    if exclude_id is not None:
        qs = qs.exclude(id=exclude_id)
    return qs


def _overlaps(
    partner_id: UUID,
    branch_id: UUID | None,
    test_category: str | None,
    effective_from: date,
    exclude_id: UUID | None = None,
) -> bool:
    """RR-7: a new open-ended rule overlaps iff an existing bucket rule is
    open or ends on/after the candidate's effective_from."""
    return (
        _bucket_rules(partner_id, branch_id, test_category, exclude_id)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=effective_from))
        .exists()
    )


class RuleService:
    """Revenue-share rule CRUD + specificity (Doc 05 §5.2–§5.4). Owner only."""

    @staticmethod
    def get_rule(rule_id: UUID) -> RevenueShareRule:
        try:
            return RevenueShareRule.objects.select_related(
                "referral_partner", "branch"
            ).get(id=rule_id)
        except RevenueShareRule.DoesNotExist as exc:
            raise PartnerError(
                "not_found",
                "Revenue-share rule not found.",
                status.HTTP_404_NOT_FOUND,
            ) from exc

    @staticmethod
    def list_rules(partner_id: UUID) -> Any:
        PartnerService.get_partner(partner_id)  # 404 for unknown/deleted partner
        return (
            RevenueShareRule.objects.filter(referral_partner_id=partner_id)
            .select_related("branch")
            .order_by("-effective_from", "-created_at")
        )

    @staticmethod
    @transaction.atomic
    def create_rule(
        actor: StaffUser,
        partner_id: UUID,
        payload: dict[str, Any],
        ip: str = "",
    ) -> RevenueShareRule:
        PartnerService.get_partner(partner_id)
        branch_id = payload.get("branch_id")
        branch = None
        if branch_id is not None:
            try:
                branch = Branch.objects.get(id=branch_id)
            except Branch.DoesNotExist as exc:
                raise PartnerError(
                    "unknown_branch",
                    "Branch not found.",
                    status.HTTP_404_NOT_FOUND,
                ) from exc
        test_category = payload.get("test_category")
        effective_from = payload["effective_from"]
        if _overlaps(partner_id, branch_id, test_category, effective_from):
            raise PartnerError(
                "rule_overlap",
                "A rule in the same (partner, branch, category) bucket "
                "already applies on that date.",
            )
        rule = RevenueShareRule.objects.create(
            referral_partner_id=partner_id,
            branch=branch,
            test_category=test_category,
            percent=payload["percent"],
            effective_from=effective_from,
            effective_to=None,
        )
        _audit(
            actor,
            "rule.created",
            "revenue_share_rule",
            rule.id,
            None,
            _rule_snapshot(rule),
            ip,
        )
        return rule

    @staticmethod
    @transaction.atomic
    def update_rule(
        actor: StaffUser,
        rule_id: UUID,
        payload: dict[str, Any],
        ip: str = "",
    ) -> RevenueShareRule:
        """RR-3: close-old + insert-new. The old row's percent and
        effective_from are never mutated; only effective_to is set."""
        old = RuleService.get_rule(rule_id)
        new_percent: Decimal = payload.get("percent", old.percent)
        new_from: date = payload.get("effective_from", _today())

        # RR-4: no retroactive edits.
        if new_from <= old.effective_from:
            raise PartnerError(
                "rule_retroactive",
                "The new effective_from must be after the current rule's "
                "effective_from. Close later rules first.",
            )
        # The old row is already closed: the new row must continue exactly
        # where it ended. Moving the old end date forward would retroactively
        # rewrite history; moving it back would shrink it (RR-4).
        if old.effective_to is not None and new_from != old.effective_to + timedelta(
            days=1
        ):
            raise PartnerError(
                "rule_retroactive",
                "The rule is already closed; the new effective_from "
                "must be the day after its effective_to.",
            )
        if _overlaps(
            old.referral_partner_id,
            old.branch_id,
            old.test_category,
            new_from,
            exclude_id=old.id,
        ):
            raise PartnerError(
                "rule_overlap",
                "The new rule would overlap another rule in the same "
                "(partner, branch, category) bucket.",
            )

        before = _rule_snapshot(old)
        if old.effective_to is None:
            old.effective_to = new_from - timedelta(days=1)
            old.save(update_fields=["effective_to", "updated_at"])

        new_rule = RevenueShareRule.objects.create(
            referral_partner_id=old.referral_partner_id,
            branch_id=old.branch_id,
            test_category=old.test_category,
            percent=new_percent,
            effective_from=new_from,
            effective_to=None,
        )
        _audit(
            actor,
            "rule.updated",
            "revenue_share_rule",
            new_rule.id,
            before,
            _rule_snapshot(new_rule),
            ip,
        )
        return new_rule


def resolve_rule(
    partner_id: UUID,
    branch_id: UUID | None,
    categories: Iterable[str | None],
    on_date: date,
) -> RevenueShareRule | None:
    """Pick the single applicable rule by specificity (Doc 05 §5.3, RR-11).

    categories: distinct test_category values across the invoice's items.
    RR-10: a category rule matches only when every item is in that one
    category; mixed-category invoices consider NULL-category buckets only.
    Returns None for the 0% fallback (RR-11) — resolution never errors.
    """
    non_null = {c for c in categories if c}
    single = next(iter(non_null)) if len(non_null) == 1 else None

    buckets: list[tuple[UUID | None, str | None]] = [
        (branch_id, single),
        (branch_id, None),
        (None, single),
        (None, None),
    ]
    seen: set[tuple[str | None, str | None]] = set()
    for b_id, cat in buckets:
        key = (str(b_id) if b_id else None, cat)
        if key in seen:
            continue
        seen.add(key)
        qs = RevenueShareRule.objects.filter(
            referral_partner_id=partner_id,
            test_category=cat,
            effective_from__lte=on_date,
        )
        if b_id is None:
            qs = qs.filter(branch__isnull=True)
        else:
            qs = qs.filter(branch_id=b_id)
        rule = (
            qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
            .order_by("-effective_from")
            .first()
        )
        if rule is not None:
            return rule
    return None


class DashboardService:
    """Partner dashboard, computed at read time (Doc 05 §10). Owner only."""

    @staticmethod
    def get_dashboard(partner_id: UUID) -> dict[str, Any]:
        partner = PartnerService.get_partner(partner_id)
        year_start = (
            timezone.now()
            .astimezone(KARACHI)
            .replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        )

        entries = ShareLedgerEntry.objects.filter(referral_partner_id=partner.id)
        ytd_earned = entries.filter(created_at__gte=year_start).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        # An entry is "in a settlement" when a settlement_line points at it
        # from a non-cancelled settlement. Everything else is pending (§12.5).
        live_lines = SettlementLine.objects.filter(
            share_ledger_entry__referral_partner_id=partner.id
        ).exclude(settlement__status=Settlement.Status.CANCELLED)
        settled_ids = set(live_lines.values_list("share_ledger_entry_id", flat=True))

        ytd_settled = entries.filter(
            id__in=settled_ids, created_at__gte=year_start
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        pending_total = entries.exclude(id__in=settled_ids).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        # late_entries (§12.5, CF-2/CF-3): pending entries whose period
        # already has a DRAFT/APPROVED/SENT/PAID settlement.
        pending_periods = set(
            entries.exclude(id__in=settled_ids).values_list("period", flat=True)
        )
        closed_periods = set(
            Settlement.objects.filter(
                referral_partner_id=partner.id,
                period__in=pending_periods,
            )
            .exclude(status=Settlement.Status.CANCELLED)
            .values_list("period", flat=True)
        )
        late_entries = (
            entries.exclude(id__in=settled_ids)
            .filter(period__in=closed_periods)
            .count()
        )

        last_6 = list(
            Settlement.objects.filter(referral_partner_id=partner.id).order_by(
                "-period"
            )[:6]
        )

        return {
            "partner_id": partner.id,
            "partner_name": partner.name,
            "has_email": bool(partner.email),
            "ytd_earned": f"{ytd_earned:.2f}",
            "ytd_settled": f"{ytd_settled:.2f}",
            "pending_total": f"{pending_total:.2f}",
            "late_entries": late_entries,
            "last_6_settlements": last_6,
        }


logger = logging.getLogger(__name__)

# Asia/Karachi timezone for period computation (Doc 05 §6.5: YYYY-MM, Asia/Karachi)
KARACHI_TZ = timezone.get_fixed_timezone(300)  # UTC+5


def _quantize(amount: Decimal) -> Decimal:
    """Quantize to 0.01 with ROUND_HALF_UP (Doc 05 §6.6, RS-7)."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _current_period() -> str:
    """Current YYYY-MM period in Asia/Karachi."""
    now = timezone.now().astimezone(KARACHI_TZ)
    return now.strftime("%Y-%m")


def _resolve_ledger_rule(
    *,
    partner: ReferralPartner,
    branch_id: Any | None,
    test_category: str | None,
    on_date: date,
) -> RevenueShareRule | None:
    """Resolve the applicable revenue-share rule per Doc 05 §5.3 specificity order.

    Rank 1: (partner, branch, category) — most specific
    Rank 2: (partner, branch, NULL)
    Rank 3: (partner, NULL, category)
    Rank 4: (partner, NULL, NULL) — least specific (general rate)

    Returns None when no rule matches (0% fallback, §5.4).
    """
    # Build the four buckets in specificity order
    candidates: list[dict[str, Any]] = [
        {"branch_id": branch_id, "test_category": test_category},  # Rank 1
        {"branch_id": branch_id, "test_category": None},  # Rank 2
        {"branch_id": None, "test_category": test_category},  # Rank 3
        {"branch_id": None, "test_category": None},  # Rank 4
    ]

    for bucket in candidates:
        # Skip rank 1 if both branch and category are None (same as rank 4)
        # Skip rank 2 if branch is None (same as rank 4)
        # Skip rank 3 if category is None (same as rank 4)
        # This avoids duplicate queries but keeps logic clear
        query = RevenueShareRule.objects.filter(
            referral_partner=partner,
            effective_from__lte=on_date,
        ).filter(
            # effective_to is NULL (still in force) or on_date <= effective_to
            Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)
        )

        if bucket["branch_id"] is not None:
            query = query.filter(branch_id=bucket["branch_id"])
        else:
            query = query.filter(branch__isnull=True)

        if bucket["test_category"] is not None:
            query = query.filter(test_category=bucket["test_category"])
        else:
            query = query.filter(test_category__isnull=True)

        rule = query.first()
        if rule is not None:
            return rule

    return None


def _get_invoice_category(invoice: Any) -> str | None:
    """Get the test category for rule resolution.

    For now, uses the first invoice item's test category. This is a
    simplification; full per-line category resolution is out of scope for v1.
    """
    # Try to get category from invoice items
    try:
        first_item = invoice.items.first()
        if first_item is not None and hasattr(first_item, "test"):
            test = first_item.test
            if test is not None:
                return getattr(test, "category", None)
    except Exception:
        pass
    return None


def record_share_entry(payment: Any) -> ShareLedgerEntry | None:
    """Synchronous consumer for billing.payment_recorded (Doc 05 §6.2, SL-1–SL-7).

    Called by the billing service after the payment insert and before commit,
    inside the same transaction. Writes at most one share_ledger_entry row.

    Returns the created (or existing, on idempotent replay) entry, or None
    when no row is written (walk-in, zero-amount skip).

    SL-2: Walk-in (no referral_partner) → no row.
    SL-5: UNIQUE(payment_id) → idempotent; duplicate returns existing.
    SL-6/§6.6: Zero-amount (quantized to 0.00) → skip, no row.
    """
    from apps.billing.models import Payment

    # Only process PAYMENT kind here; refunds go through record_reversal
    if payment.kind != Payment.Kind.PAYMENT:
        return None

    invoice = payment.invoice

    # SL-2: Walk-in — no partner, no row
    if invoice.referral_partner_id is None:
        logger.debug(
            "Share ledger: walk-in payment %s, no partner, skipping",
            payment.id,
        )
        return None

    # Idempotency: check for existing row first (SL-5)
    existing = ShareLedgerEntry.objects.filter(payment=payment).first()
    if existing is not None:
        logger.debug(
            "Share ledger: payment %s already has entry %s, returning existing",
            payment.id,
            existing.id,
        )
        return existing

    partner = invoice.referral_partner
    branch_id = invoice.branch_id
    test_category = _get_invoice_category(invoice)
    on_date = payment.created_at.astimezone(KARACHI_TZ).date()

    # Rule resolution at write time (spec: snapshot percent_applied + rule_id)
    rule = _resolve_ledger_rule(
        partner=partner,
        branch_id=branch_id,
        test_category=test_category,
        on_date=on_date,
    )

    # §5.4: No rule matched → 0% fallback, no row (SL-10 analog for payments)
    # Actually, re-reading SL-1: percent_applied stores the percent used.
    # If no rule matches, percent is 0, amount is 0, and zero-amount skip applies.
    percent = rule.percent if rule is not None else Decimal("0.00")

    # SL-1: amount = payment.amount × rule.percent / 100, Decimal, quantized
    basis_amount = payment.amount
    raw_amount = basis_amount * percent / Decimal("100")
    amount = _quantize(raw_amount)

    # §6.6/SL-13: Zero-amount skip — quantized to 0.00 → no row
    if amount == Decimal("0.00"):
        logger.debug(
            "Share ledger: payment %s computed zero amount (percent=%s), skipping",
            payment.id,
            percent,
        )
        return None

    period = _current_period()

    # Insert with conflict handling on payment_id (SL-5: idempotent)
    try:
        with transaction.atomic():
            entry = ShareLedgerEntry.objects.create(
                payment=payment,
                referral_partner=partner,
                rule=rule,
                amount=amount,
                percent_applied=percent,
                basis_amount=basis_amount,
                period=period,
            )
            logger.info(
                "Share ledger: created entry %s for payment %s "
                "(partner=%s, percent=%s, amount=%s)",
                entry.id,
                payment.id,
                partner.id,
                percent,
                amount,
            )
            return entry
    except IntegrityError:
        # Concurrent insert with same payment_id: return existing (SL-5)
        existing = ShareLedgerEntry.objects.filter(payment=payment).first()
        if existing is not None:
            logger.debug(
                "Share ledger: concurrent insert for payment %s, returning existing %s",
                payment.id,
                existing.id,
            )
            return existing
        raise


def _is_period_closed(partner: ReferralPartner, period: str) -> bool:
    """Check if a period is closed (settlement APPROVED/SENT/PAID)."""
    return Settlement.objects.filter(
        referral_partner=partner,
        period=period,
        status__in=[
            Settlement.Status.APPROVED,
            Settlement.Status.SENT,
            Settlement.Status.PAID,
        ],
    ).exists()


def _has_live_settlement(partner: ReferralPartner, period: str) -> bool:
    """Check if a period has a live (non-cancelled) settlement."""
    return (
        Settlement.objects.filter(
            referral_partner=partner,
            period=period,
        )
        .exclude(
            status=Settlement.Status.CANCELLED,
        )
        .exists()
    )


def _route_reversal_period(
    *,
    original_entry: ShareLedgerEntry,
    refund_payment: Any,
) -> str:
    """Route the reversal's period per SL-11.

    - Original period closed (APPROVED/SENT/PAID) → refund's YYYY-MM (current)
    - Original period has live DRAFT → refund's YYYY-MM (current)
    - Otherwise → original period (settle together)
    """
    partner = original_entry.referral_partner
    original_period = original_entry.period

    if _is_period_closed(partner, original_period):
        # Closed → current open period (refund's YYYY-MM)
        return refund_payment.created_at.astimezone(KARACHI_TZ).strftime("%Y-%m")

    if _has_live_settlement(partner, original_period):
        # Live DRAFT exists → refund's YYYY-MM (joins next cycle)
        return refund_payment.created_at.astimezone(KARACHI_TZ).strftime("%Y-%m")

    # Otherwise → original period (settle together, net correctly)
    return original_period


def record_reversal(refund_payment: Any) -> ShareLedgerEntry | None:
    """Record a refund reversal entry (Doc 05 §6.5, SL-8–SL-12).

    SL-8: Copies percent_applied + rule_id from original (never re-resolves).
    SL-9: amount = -(refund.amount × percent_applied / 100), quantized.
    SL-10: Original had no row → refund produces no row.
    SL-11: Period routing per original entry's settlement state.
    SL-12: Partial refunds reverse partially; each writes its own row.
    """
    from apps.billing.models import Payment

    if refund_payment.kind != Payment.Kind.REFUND:
        return None

    # Find the original payment's ledger entry
    # The refund references the invoice; we need the original payment(s)
    # For simplicity: find the most recent payment entry for this invoice
    # that hasn't been fully reversed. In practice, refunds are linked
    # to specific payments via the invoice.
    invoice = refund_payment.invoice

    # Get all payment (non-refund) entries for this invoice, ordered by created
    original_entries = (
        ShareLedgerEntry.objects.filter(
            payment__invoice=invoice,
            payment__kind=Payment.Kind.PAYMENT,
            amount__gt=Decimal("0.00"),  # Only positive (accrual) entries
        )
        .select_related("payment", "referral_partner", "rule")
        .order_by("payment__created_at")
    )

    # SL-10: No original row → no reversal row
    if not original_entries.exists():
        logger.debug(
            "Share ledger: refund %s has no original entry, skipping reversal",
            refund_payment.id,
        )
        return None

    # For now, use the first (oldest) original entry.
    # A full implementation would track which payments have been reversed
    # and allocate the refund across them. This is a v1 simplification
    # that handles the common single-payment case correctly.
    original = original_entries.first()
    assert original is not None

    # Idempotency: check if this refund already has a reversal
    existing = ShareLedgerEntry.objects.filter(payment=refund_payment).first()
    if existing is not None:
        return existing

    # SL-8: Copy percent_applied + rule_id from original (never re-resolve)
    percent_applied = original.percent_applied
    rule = original.rule
    partner = original.referral_partner

    # SL-9: amount = -(refund.amount × percent_applied / 100)
    basis_amount = refund_payment.amount
    raw_amount = -(basis_amount * percent_applied / Decimal("100"))
    amount = _quantize(raw_amount)

    # SL-10: Zero-reversal skip
    if amount == Decimal("0.00"):
        logger.debug(
            "Share ledger: refund %s computed zero reversal, skipping",
            refund_payment.id,
        )
        return None

    # SL-11: Period routing
    period = _route_reversal_period(
        original_entry=original,
        refund_payment=refund_payment,
    )

    try:
        with transaction.atomic():
            entry = ShareLedgerEntry.objects.create(
                payment=refund_payment,
                referral_partner=partner,
                rule=rule,
                amount=amount,  # Negative (compensating entry)
                percent_applied=percent_applied,
                basis_amount=basis_amount,
                period=period,
            )
            logger.info(
                "Share ledger: created reversal %s for refund %s "
                "(original=%s, amount=%s, period=%s)",
                entry.id,
                refund_payment.id,
                original.id,
                amount,
                period,
            )
            return entry
    except IntegrityError:
        existing = ShareLedgerEntry.objects.filter(payment=refund_payment).first()
        if existing is not None:
            return existing
        raise


def reconcile_missing_ledger_entries() -> dict[str, int]:
    """Hourly Beat sweep: replay record_share_entry for missing rows (SL-6, SL-7).

    Scans for partner-attributed payments with no ledger row and replays
    record_share_entry() for each. In a correct system, finds none.
    Returns {tenant_slug: repaired_count} for metrics/alerting.
    A non-zero count is a bug report, not a routine event.
    """
    from django_tenants.utils import schema_context

    from apps.billing.models import Payment
    from apps.core.models import Tenant

    results: dict[str, int] = {}

    # Per-tenant fan-out (Doc 04 §13.2)
    for tenant in Tenant.objects.exclude(schema_name="public"):
        repaired = 0
        try:
            with schema_context(tenant.schema_name):
                # Find partner-attributed payments with no ledger row
                payments_without_entry = (
                    Payment.objects.filter(
                        kind=Payment.Kind.PAYMENT,
                        invoice__referral_partner__isnull=False,
                    )
                    .exclude(id__in=ShareLedgerEntry.objects.values("payment_id"))
                    .select_related("invoice", "invoice__referral_partner")
                    .order_by("created_at")
                )

                for payment in payments_without_entry:
                    try:
                        result = record_share_entry(payment)
                        if result is not None:
                            repaired += 1
                            logger.warning(
                                "Share ledger sweep: repaired missing entry "
                                "for payment %s (tenant=%s)",
                                payment.id,
                                tenant.schema_name,
                            )
                    except Exception as exc:
                        logger.error(
                            "Share ledger sweep: failed to repair payment %s "
                            "(tenant=%s): %s",
                            payment.id,
                            tenant.schema_name,
                            exc,
                        )
        except Exception as exc:
            logger.error(
                "Share ledger sweep: tenant %s failed: %s",
                tenant.schema_name,
                exc,
            )

        results[tenant.schema_name] = repaired
        if repaired > 0:
            logger.warning(
                "Share ledger sweep: tenant %s repaired %d entries "
                "(non-zero is a bug report)",
                tenant.schema_name,
                repaired,
            )

    return results
