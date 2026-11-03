"""Business logic for the referral-partner registry (Doc 05 §5.1–§5.4, §10,
§12.5; KAN-164 / LAB-39).

Thin views call into these services. All state changes run inside a single
transaction that also writes the audit row (RP-6). Money stays Decimal.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
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
