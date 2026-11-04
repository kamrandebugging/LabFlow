"""Settlement workflow service (Doc 05 §7.3–§7.6, §10; KAN-261 / LAB-42).

State machine (Doc 05 §7.3):
    DRAFT --approve--> APPROVED --(n8n callback)--> SENT --mark-paid--> PAID
    DRAFT --cancel--> CANCELLED  (entries become pending again, re-draft = new row)

Rules:
- approve: Owner only, DRAFT only (409 invalid_state_transition), If-Match
  required (409 version_conflict on stale token), read-only subscription
  → 403 subscription_read_only. Sets APPROVED + approved_by/at, one audit
  row, enqueues referral_partners.finalize_settlement (ST-9, ST-10).
- cancel: Owner only, DRAFT only — anything else → 422
  settlement_not_cancellable (ST-16). Lines stay; ledger rows never change
  (ST-17). Entries are pending again by derivation (ST-18).
- mark-paid: Owner only, SENT only (409 invalid_state_transition). The
  reference is recorded in the audit row only — Doc 02 has no column
  (ST-14). PAID is terminal for the money flow (ST-15).
- send: Owner only, APPROVED or SENT only (409 invalid_state_transition).
  Missing partner email → 422 partner_email_missing (ST-20). Creates a
  fresh notification row per attempt (DL-6); the failed row stays.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.core.models import Subscription
from apps.notifications.models import Notification
from apps.partners.models import Settlement, SettlementLine

logger = logging.getLogger(__name__)

# Doc 04 §11.2: grace period before past_due becomes read-only.
_GRACE_DAYS = 14

# Doc 05 §9 / DL-3: notification template for statement delivery.
SETTLEMENT_READY_TEMPLATE = "settlement_ready"

# Celery task enqueued on approval (ST-10). The PDF render itself is
# implemented in the statement-PDF story; the task is idempotent.
FINALIZE_TASK_NAME = "referral_partners.finalize_settlement"


class SettlementError(Exception):
    """Base error carrying a machine-stable code and HTTP status."""

    error_code = "settlement_error"
    status_code = 500

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.error_code)


class SettlementNotFoundError(SettlementError):
    error_code = "not_found"
    status_code = 404


class InvalidStateTransitionError(SettlementError):
    error_code = "invalid_state_transition"
    status_code = 409


class VersionConflictError(SettlementError):
    error_code = "version_conflict"
    status_code = 409


class IfMatchRequiredError(SettlementError):
    error_code = "if_match_required"
    status_code = 400


class SettlementNotCancellableError(SettlementError):
    error_code = "settlement_not_cancellable"
    status_code = 422


class PartnerEmailMissingError(SettlementError):
    error_code = "partner_email_missing"
    status_code = 422


class SubscriptionReadOnlyError(SettlementError):
    error_code = "subscription_read_only"
    status_code = 403


class ForbiddenError(SettlementError):
    error_code = "forbidden"
    status_code = 403


class ValidationError(SettlementError):
    error_code = "validation_error"
    status_code = 422


def settlement_etag(settlement: Settlement) -> str:
    """Version token for If-Match (Doc 05 AP-2: updated_at-derived ETag)."""
    return settlement.updated_at.isoformat()


def _check_if_match(settlement: Settlement, if_match: str | None) -> None:
    """AP-2: mutating settlement actions require a current If-Match token."""
    if not if_match:
        raise IfMatchRequiredError("The If-Match header is required.")
    clean = if_match.strip().strip('"').strip("'")
    current = settlement_etag(settlement)
    if clean not in (current, str(settlement.updated_at)):
        raise VersionConflictError(
            "Settlement was modified since the version you hold."
        )


def tenant_access_mode(tenant: Any) -> str:
    """Return 'full' or 'read_only' for the tenant (Doc 04 §11.2 seam).

    LAB-36 owns the canonical implementation; this seam mirrors its rule so
    LAB-42 enforces read-only correctly on main without LAB-36 merged:
    active → full; past_due within 14 days → full (grace); past_due beyond
    grace / cancelled / expired / no subscription → read_only.
    """
    try:
        with schema_context("public"):
            sub = (
                Subscription.objects.filter(tenant_id=tenant.id)
                .order_by("-created_at")
                .first()
            )
    except Exception:  # pragma: no cover - defensive; never crash the request
        logger.exception("tenant_access_mode lookup failed")
        return "read_only"
    if sub is None:
        return "read_only"
    if sub.status == Subscription.Status.ACTIVE:
        return "full"
    if sub.status == Subscription.Status.PAST_DUE:
        if timezone.now() - sub.updated_at <= timedelta(days=_GRACE_DAYS):
            return "full"
        return "read_only"
    return "read_only"


def _require_owner(actor: StaffUser) -> None:
    if actor.role != Role.OWNER:
        raise ForbiddenError("Only the Owner may perform this action.")


def _require_writable(actor: StaffUser, tenant: Any) -> None:
    """RS-37: writes are refused in read-only subscription mode."""
    if tenant_access_mode(tenant) != "full":
        raise SubscriptionReadOnlyError(
            "Subscription is read-only; this action is paused."
        )


def _audit(
    actor: StaffUser,
    action: str,
    settlement: Settlement,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    ip: str | None,
    user_agent: str | None,
) -> None:
    AuditLog.objects.create(
        actor_id=actor.id,
        action=action,
        entity_type="settlement",
        entity_id=settlement.id,
        before_jsonb=before,
        after_jsonb=after,
        ip=ip or "",
        user_agent=user_agent or "",
    )


class SettlementService:
    """State transitions for monthly partner settlements (Doc 05 §7)."""

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    def get_settlement(settlement_id: uuid.UUID) -> Settlement:
        try:
            return Settlement.objects.select_related("referral_partner").get(
                id=settlement_id
            )
        except Settlement.DoesNotExist as exc:
            raise SettlementNotFoundError("Settlement not found.") from exc

    @staticmethod
    def list_settlements(
        partner_id: uuid.UUID | None = None,
        period: str | None = None,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[Settlement], str | None]:
        """Cursor-paginated list (Doc 03 §6.1). Unknown status → 422."""
        qs = Settlement.objects.select_related("referral_partner").order_by(
            "-created_at", "-id"
        )
        if partner_id is not None:
            qs = qs.filter(referral_partner_id=partner_id)
        if period is not None:
            qs = qs.filter(period=period)
        if status is not None:
            valid = {c for c, _ in Settlement.Status.choices}
            if status not in valid:
                raise ValidationError(f"Unknown status filter: {status}.")
            qs = qs.filter(status=status)
        try:
            limit_value = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            limit_value = 50
        if cursor:
            try:
                cursor_uuid = uuid.UUID(cursor)
                anchor = Settlement.objects.get(id=cursor_uuid)
                qs = qs.filter(created_at__lt=anchor.created_at) | qs.filter(
                    created_at=anchor.created_at, id__lt=anchor.id
                )
            except (ValueError, Settlement.DoesNotExist) as exc:
                raise ValidationError("Invalid cursor.") from exc
        rows = list(qs[: limit_value + 1])
        next_cursor = str(rows[-1].id) if len(rows) > limit_value else None
        return rows[:limit_value], next_cursor

    # ------------------------------------------------------------------
    # Approve (ST-9, ST-10)
    # ------------------------------------------------------------------

    @classmethod
    def approve(
        cls,
        actor: StaffUser,
        tenant: Any,
        settlement_id: uuid.UUID,
        if_match: str | None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Settlement:
        _require_owner(actor)
        _require_writable(actor, tenant)
        settlement = cls.get_settlement(settlement_id)
        _check_if_match(settlement, if_match)
        if settlement.status != Settlement.Status.DRAFT:
            raise InvalidStateTransitionError(
                "Only a DRAFT settlement can be approved."
            )

        before = {"status": settlement.status}
        with transaction.atomic():
            settlement.status = Settlement.Status.APPROVED
            settlement.approved_by = actor
            settlement.approved_at = timezone.now()
            # ST-12: total is never recomputed at approval.
            settlement.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                    "updated_at",
                ]
            )
            _audit(
                actor,
                "settlement.approved",
                settlement,
                before,
                {
                    "status": "APPROVED",
                    "approved_by": str(actor.id),
                    "total": str(settlement.total),
                },
                ip,
                user_agent,
            )
        # ST-10: enqueue the finalize task (PDF + delivery webhook).
        # Eager in tests (CELERY_TASK_ALWAYS_EAGER); queued in production.
        from apps.partners.tasks import finalize_settlement

        finalize_settlement.delay(tenant.schema_name, str(settlement.id))
        settlement.refresh_from_db()
        return settlement

    # ------------------------------------------------------------------
    # Cancel (ST-16..ST-19)
    # ------------------------------------------------------------------

    @classmethod
    def cancel(
        cls,
        actor: StaffUser,
        tenant: Any,
        settlement_id: uuid.UUID,
        if_match: str | None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Settlement:
        _require_owner(actor)
        _require_writable(actor, tenant)
        settlement = cls.get_settlement(settlement_id)
        _check_if_match(settlement, if_match)
        if settlement.status != Settlement.Status.DRAFT:
            # ST-16: money promised or paid is not un-promised by a button.
            raise SettlementNotCancellableError(
                "Only a DRAFT settlement can be cancelled."
            )

        before = {"status": settlement.status}
        with transaction.atomic():
            settlement.status = Settlement.Status.CANCELLED
            settlement.save(update_fields=["status", "updated_at"])
            _audit(
                actor,
                "settlement.cancelled",
                settlement,
                before,
                {"status": "CANCELLED"},
                ip,
                user_agent,
            )
        # ST-17/ST-18: lines stay on the cancelled settlement; ledger rows
        # never change; entries are pending again by derivation (§6.7).
        settlement.refresh_from_db()
        return settlement

    # ------------------------------------------------------------------
    # Mark paid (ST-13..ST-15)
    # ------------------------------------------------------------------

    @classmethod
    def mark_paid(
        cls,
        actor: StaffUser,
        tenant: Any,
        settlement_id: uuid.UUID,
        if_match: str | None,
        reference: str | None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Settlement:
        _require_owner(actor)
        _require_writable(actor, tenant)
        settlement = cls.get_settlement(settlement_id)
        _check_if_match(settlement, if_match)
        if settlement.status != Settlement.Status.SENT:
            raise InvalidStateTransitionError(
                "Only a SENT settlement can be marked paid."
            )
        if not reference or not reference.strip():
            raise ValidationError("A payment reference is required.")

        before = {"status": settlement.status}
        with transaction.atomic():
            settlement.status = Settlement.Status.PAID
            settlement.save(update_fields=["status", "updated_at"])
            # ST-14: the reference, actor and time live in the audit row
            # only — Doc 02 has no paid_by/paid_at columns.
            _audit(
                actor,
                "settlement.mark_paid",
                settlement,
                before,
                {
                    "status": "PAID",
                    "reference": reference.strip(),
                    "confirmed_at": timezone.now().isoformat(),
                },
                ip,
                user_agent,
            )
        # ST-15: PAID changes nothing in the ledger.
        settlement.refresh_from_db()
        return settlement

    # ------------------------------------------------------------------
    # Send (DL-6)
    # ------------------------------------------------------------------

    @classmethod
    def send(
        cls,
        actor: StaffUser,
        tenant: Any,
        settlement_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Notification:
        _require_owner(actor)
        _require_writable(actor, tenant)
        settlement = cls.get_settlement(settlement_id)
        if settlement.status not in (
            Settlement.Status.APPROVED,
            Settlement.Status.SENT,
        ):
            raise InvalidStateTransitionError(
                "Only an APPROVED or SENT settlement can be sent."
            )
        partner = settlement.referral_partner
        if not partner.email:
            # ST-20: money owed does not depend on an inbox.
            raise PartnerEmailMissingError("Partner has no email address on file.")

        with transaction.atomic():
            # DL-6: a re-send creates a fresh notification row — the failed
            # row stays as the record of the failure.
            notification = Notification.objects.create(
                template_key=SETTLEMENT_READY_TEMPLATE,
                recipient_type=Notification.RecipientType.PARTNER,
                recipient_id=partner.id,
                channel=Notification.Channel.EMAIL,
                status=Notification.Status.PENDING,
                idempotency_key=(f"settlement:{settlement.id}:send:{uuid.uuid4().hex}"),
            )
            _audit(
                actor,
                "settlement.send",
                settlement,
                {"status": settlement.status},
                {
                    "status": settlement.status,
                    "notification_id": str(notification.id),
                    "recipient_email": partner.email,
                },
                ip,
                user_agent,
            )
        return notification

    # ------------------------------------------------------------------
    # Serializers (read models)
    # ------------------------------------------------------------------

    @staticmethod
    def to_dict(settlement: Settlement, include_lines: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": str(settlement.id),
            "referral_partner_id": str(settlement.referral_partner_id),
            "period": settlement.period,
            "status": settlement.status,
            "total": format(settlement.total, ".2f"),
            "statement_pdf_key": settlement.statement_pdf_key,
            "approved_by": (
                str(settlement.approved_by_id) if settlement.approved_by_id else None
            ),
            "approved_at": (
                settlement.approved_at.isoformat() if settlement.approved_at else None
            ),
            "version": settlement_etag(settlement),
            "created_at": settlement.created_at.isoformat(),
            "updated_at": settlement.updated_at.isoformat(),
        }
        if include_lines:
            lines = (
                SettlementLine.objects.filter(settlement=settlement)
                .select_related("share_ledger_entry")
                .order_by("created_at", "id")
            )
            data["lines"] = [
                {
                    "id": str(line.id),
                    "share_ledger_entry_id": str(line.share_ledger_entry_id),
                    "amount": format(line.amount, ".2f"),
                    "entry_period": line.share_ledger_entry.period,
                }
                for line in lines
            ]
        return data
