"""Business logic for the Billing module (Doc 03 §5.3, §6.4, KAN-124 / LAB-18,
KAN-130 / LAB-19).

Invoice creation (original LAB-20):
- BL-1: one patient + one branch; test_id XOR panel_id; description + unit_price
  snapshotted at creation via catalog get_effective_price (CT-3 → test_not_priced).
- BL-2: server computes subtotal/total in Decimal; client totals ignored.
- BL-3: discount > 0 requires reason + Manager/Owner role.
- BL-4: Idempotency-Key stored (partial UNIQUE); replay → original (200);
  reused key + different payload → 409 idempotency_key_reused.
- BL-6: zero-total invoice created directly in paid; otherwise unpaid.
- BL-V2: duplicate same-kind lines merged by summing qty.
- Audit: invoice.created row in the same DB transaction (BL-V3: received_by =
  authenticated actor, recorded on the audit row).

Payments + refunds (original LAB-21):
- BL-4: Idempotency-Key required; stored on the payment row (partial UNIQUE);
  replay same key + payload → original (200); reused key + different payload →
  409 idempotency_key_reused.
- BL-5: payments are append-only; kind (payment|refund) supplies the sign;
  amount always positive. Rows are never updated or deleted.
- BL-6: invoice.status is DERIVED from payment rows in the SAME transaction as
  the payment insert: net = Σ payments − Σ refunds; net = total → paid;
  net = 0 with ≥1 payment and ≥1 refund → refunded; 0 < net < total → partial;
  otherwise unpaid.
- BL-7: payment rejected when net would exceed total (422 overpayment); refund
  rejected when cumulative refunds would exceed cumulative payments
  (422 refund_exceeds_payments). Refund ceiling (interim, Doc 05 §13 OQ-31):
  Manager alone up to 5000; above requires Owner (403 owner_approval_required).
- BL-10: reference required for every non-cash method and for all refunds
  (422 reference_required).
- Events: billing.payment_recorded fired on every payment row (consumed by
  Doc 05 Phase 3); refunds additionally carry the Doc 05 share-reversal hook.
  No event bus exists yet — events are recorded on the audit row's after_jsonb
  (same transaction), which the future bus will consume.
- Audit: payment.recorded / payment.refunded rows in the same DB transaction
  (BL-V3: received_by = authenticated actor).
"""

import base64
import binascii
import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.branches.models import Branch
from apps.catalog.models import Panel, Test
from apps.catalog.services import CatalogService
from apps.partners.models import ReferralPartner
from apps.patients.models import Patient
from apps.samples.models import Sample

BILLING_WRITE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
BILLING_READ_ROLES = {
    Role.OWNER,
    Role.MANAGER,
    Role.RECEPTION,
    Role.TECHNICIAN,
    Role.PATHOLOGIST,
}
DISCOUNT_ROLES = {Role.OWNER, Role.MANAGER}
PAYMENT_WRITE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
REFUND_ROLES = {Role.OWNER, Role.MANAGER}
# Interim refund ceiling (Doc 05 §13, OQ-31): a Manager alone may refund up to
# this amount; anything above requires the Owner.
REFUND_MANAGER_CEILING = Decimal("5000.00")


class BillingError(Exception):
    """Base billing error carrying an HTTP status + machine code."""

    __test__ = False
    status_code = 422
    error_code = "billing_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.error_code)


class BillingNotFoundError(BillingError):
    status_code = 404
    error_code = "not_found"


class DiscountNotPermittedError(BillingError):
    status_code = 403
    error_code = "discount_not_permitted"


class DiscountReasonRequiredError(BillingError):
    status_code = 422
    error_code = "discount_reason_required"


class DiscountExceedsSubtotalError(BillingError):
    status_code = 422
    error_code = "discount_exceeds_subtotal"


class IdempotencyKeyReusedError(BillingError):
    status_code = 409
    error_code = "idempotency_key_reused"


class RefundNotPermittedError(BillingError):
    status_code = 403
    error_code = "refund_not_permitted"


class OwnerApprovalRequiredError(BillingError):
    status_code = 403
    error_code = "owner_approval_required"


class OverpaymentError(BillingError):
    status_code = 422
    error_code = "overpayment"


class RefundExceedsPaymentsError(BillingError):
    status_code = 422
    error_code = "refund_exceeds_payments"


class ReferenceRequiredError(BillingError):
    status_code = 422
    error_code = "reference_required"


class InvalidStateTransitionError(BillingError):
    status_code = 409
    error_code = "invalid_state_transition"


class CancelReasonRequiredError(BillingError):
    status_code = 422
    error_code = "cancel_reason_required"


class InvalidFilterError(BillingError):
    status_code = 422
    error_code = "invalid_filter"


def _canonical_payload(
    *,
    patient_id: uuid.UUID,
    branch_id: uuid.UUID,
    referral_partner_id: uuid.UUID | None,
    merged_items: list[dict[str, Any]],
    discount_amount: Decimal,
    discount_reason: str | None,
) -> str:
    """Deterministic payload fingerprint for BL-4 replay comparison."""
    payload = {
        "patient_id": str(patient_id),
        "branch_id": str(branch_id),
        "referral_partner_id": str(referral_partner_id)
        if referral_partner_id
        else None,
        "items": sorted(
            [
                {
                    "kind": i["kind"],
                    "entity_id": str(i["entity_id"]),
                    "qty": i["qty"],
                }
                for i in merged_items
            ],
            key=lambda i: (i["kind"], i["entity_id"]),
        ),
        "discount_amount": f"{discount_amount:.2f}",
        "discount_reason": discount_reason,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class BillingService:
    """Invoice creation with snapshotting, idempotency and audit (KAN-124)."""

    @staticmethod
    def create_invoice(
        *,
        patient_id: uuid.UUID,
        branch_id: uuid.UUID,
        referral_partner_id: uuid.UUID | None,
        items: list[dict[str, Any]],
        discount_amount: Decimal,
        discount_reason: str | None,
        idempotency_key: str,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[Invoice, bool]:
        """Create an invoice; returns (invoice, created).

        created=False means idempotent replay of the same key + payload.
        Raises BillingError subclasses (mapped to HTTP by the view) or
        TestNotPricedError from the catalog (mapped to 422 test_not_priced).
        """
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            raise BillingNotFoundError("Patient not found.") from None
        try:
            branch = Branch.objects.get(pk=branch_id)
        except Branch.DoesNotExist:
            raise BillingNotFoundError("Branch not found.") from None
        partner = None
        if referral_partner_id is not None:
            try:
                partner = ReferralPartner.objects.get(pk=referral_partner_id)
            except ReferralPartner.DoesNotExist:
                raise BillingNotFoundError("Referral partner not found.") from None

        # BL-3: discount gates.
        if discount_amount > Decimal("0.00"):
            if actor.role not in DISCOUNT_ROLES:
                raise DiscountNotPermittedError(
                    "Only a Manager or Owner may apply a discount."
                )
            if not discount_reason:
                raise DiscountReasonRequiredError(
                    "A discount requires a discount_reason."
                )

        # BL-V2: merge duplicate same-kind lines by summing qty.
        merged: dict[tuple[str, uuid.UUID], int] = {}
        for line in items:
            test_id = line.get("test_id")
            panel_id = line.get("panel_id")
            if test_id is not None:
                key = ("test", uuid.UUID(str(test_id)))
            else:
                key = ("panel", uuid.UUID(str(panel_id)))
            merged[key] = merged.get(key, 0) + int(line["qty"])

        # BL-1: resolve entities + snapshot description/unit_price via
        # catalog effective pricing (raises TestNotPricedError → 422).
        priced_lines: list[dict[str, Any]] = []
        subtotal = Decimal("0.00")
        for (kind, entity_id), qty in merged.items():
            entity: Test | Panel
            if kind == "test":
                try:
                    entity = Test.objects.get(pk=entity_id)
                except Test.DoesNotExist:
                    raise BillingNotFoundError("Test not found.") from None
                unit_price = CatalogService.get_effective_price(
                    test_id=entity_id, branch_id=branch.id
                )
            else:
                try:
                    entity = Panel.objects.get(pk=entity_id)
                except Panel.DoesNotExist:
                    raise BillingNotFoundError("Panel not found.") from None
                unit_price = CatalogService.get_effective_price(
                    panel_id=entity_id, branch_id=branch.id
                )
            line_total = (unit_price * qty).quantize(Decimal("0.01"))
            subtotal += line_total
            priced_lines.append(
                {
                    "kind": kind,
                    "entity_id": entity_id,
                    "description": entity.name,
                    "unit_price": unit_price,
                    "qty": qty,
                    "line_total": line_total,
                }
            )

        # BL-2: server computes; discount cannot exceed subtotal.
        if discount_amount > subtotal:
            raise DiscountExceedsSubtotalError(
                "Discount cannot exceed the invoice subtotal."
            )
        total = (subtotal - discount_amount).quantize(Decimal("0.01"))

        payload_hash = hashlib.sha256(
            _canonical_payload(
                patient_id=patient.id,
                branch_id=branch.id,
                referral_partner_id=partner.id if partner else None,
                merged_items=priced_lines,
                discount_amount=discount_amount,
                discount_reason=discount_reason,
            ).encode("utf-8")
        ).hexdigest()

        # BL-6: zero-total → paid at creation; otherwise unpaid.
        initial_status = (
            Invoice.Status.PAID if total == Decimal("0.00") else Invoice.Status.UNPAID
        )

        with transaction.atomic():
            # Idempotency is scope-aware (Doc 04 §8.5): the replay lookup
            # runs through the caller's scope, so presenting another
            # branch's key cannot return another branch's invoice.
            existing = (
                Invoice.objects.scoped_to(actor)
                .filter(idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None:
                if existing.payload_sha256 != payload_hash:
                    raise IdempotencyKeyReusedError(
                        "Idempotency key was already used with a different payload."
                    )
                return existing, False

            try:
                with transaction.atomic():
                    invoice = Invoice.objects.create(
                        patient=patient,
                        branch=branch,
                        referral_partner=partner,
                        status=initial_status,
                        subtotal=subtotal,
                        discount_amount=discount_amount,
                        discount_reason=discount_reason,
                        total=total,
                        idempotency_key=idempotency_key,
                        payload_sha256=payload_hash,
                    )
                    for line in priced_lines:
                        InvoiceItem.objects.create(
                            invoice=invoice,
                            test_id=line["entity_id"]
                            if line["kind"] == "test"
                            else None,
                            panel_id=line["entity_id"]
                            if line["kind"] == "panel"
                            else None,
                            description=line["description"],
                            unit_price=line["unit_price"],
                            quantity=line["qty"],
                            line_total=line["line_total"],
                        )
            except IntegrityError:
                # Concurrent create with the same key: fall back to replay path.
                # Scoped first — a key owned by another scope is NOT returned;
                # it surfaces as key-reused (422), never as their invoice.
                existing = (
                    Invoice.objects.scoped_to(actor)
                    .filter(idempotency_key=idempotency_key)
                    .first()
                )
                if existing is None:
                    if Invoice.objects.filter(idempotency_key=idempotency_key).exists():
                        raise IdempotencyKeyReusedError(
                            "Idempotency key was already used."
                        ) from None
                    raise
                if existing.payload_sha256 != payload_hash:
                    raise IdempotencyKeyReusedError(
                        "Idempotency key was already used with a different payload."
                    ) from None
                return existing, False

            # LAB-40 (KAN-165): Synchronous revenue-share ledger consumer
            # (Doc 05 §6.2). Called after payment insert, before commit, in the
            # same transaction. If the consumer raises, the whole payment
            # transaction rolls back — no half-state.
            is_refund = kind == Payment.Kind.REFUND
            from apps.partners.services import record_reversal, record_share_entry

            if is_refund:
                record_reversal(payment)
            else:
                record_share_entry(payment)

            # Audit: immutable row in the same transaction (BL-V3: actor recorded).
            AuditLog.objects.create(
                actor_id=actor.id,
                action="invoice.created",
                entity_type="invoice",
                entity_id=invoice.id,
                before_jsonb=None,
                after_jsonb={
                    "idempotency_key": idempotency_key,
                    "patient_id": str(patient.id),
                    "branch_id": str(branch.id),
                    "subtotal": f"{subtotal:.2f}",
                    "discount_amount": f"{discount_amount:.2f}",
                    "discount_reason": discount_reason,
                    "total": f"{total:.2f}",
                    "status": initial_status,
                    "received_by": str(actor.id),
                    "item_count": len(priced_lines),
                },
                ip=ip,
                user_agent=user_agent,
            )
            return invoice, True


def _canonical_payment_payload(
    *,
    invoice_id: uuid.UUID,
    kind: str,
    method: str,
    amount: Decimal,
    reference: str | None,
) -> str:
    """Deterministic payload fingerprint for BL-4 replay comparison on payments."""
    payload = {
        "invoice_id": str(invoice_id),
        "kind": kind,
        "method": method,
        "amount": f"{amount:.2f}",
        "reference": reference,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _derive_invoice_status(
    *,
    total: Decimal,
    paid_sum: Decimal,
    refund_sum: Decimal,
) -> str:
    """BL-6: derive invoice status from payment aggregates. Never set directly."""
    net = paid_sum - refund_sum
    if net == total:
        return Invoice.Status.PAID
    if (
        net == Decimal("0.00")
        and paid_sum > Decimal("0.00")
        and refund_sum > Decimal("0.00")
    ):
        return Invoice.Status.REFUNDED
    if net == Decimal("0.00"):
        return Invoice.Status.UNPAID
    return Invoice.Status.PARTIAL


def _payment_aggregates(invoice: Invoice) -> tuple[Decimal, Decimal]:
    """Current (Σ payments, Σ refunds) for an invoice (BL-6 inputs)."""
    agg = Payment.objects.filter(invoice=invoice).aggregate(
        paid=Sum("amount", filter=Q(kind=Payment.Kind.PAYMENT)),
        refunded=Sum("amount", filter=Q(kind=Payment.Kind.REFUND)),
    )
    paid_sum: Decimal = agg["paid"] or Decimal("0.00")
    refund_sum: Decimal = agg["refunded"] or Decimal("0.00")
    return paid_sum, refund_sum


class PaymentService:
    """Payment + refund recording: append-only, idempotent, BL-6 derived (KAN-130)."""

    @staticmethod
    def record_payment(
        *,
        invoice_id: uuid.UUID,
        kind: str,
        method: str,
        amount: Decimal,
        reference: str | None,
        idempotency_key: str,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[Payment, bool]:
        """Record a payment or refund row; returns (payment, created).

        created=False means idempotent replay of the same key + payload.
        Raises BillingError subclasses (mapped to HTTP by the view).
        """
        try:
            # Layer 2 (Doc 04 §8.5): fetch through the scoped queryset —
            # an out-of-scope invoice is simply not found -> 404 (P-7).
            invoice = Invoice.objects.scoped_to(actor).get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise BillingNotFoundError("Invoice not found.") from None

        if invoice.status == Invoice.Status.CANCELLED:
            raise InvalidStateTransitionError(
                "Payments cannot be recorded on a cancelled invoice."
            )

        # Role gates: refunds are Owner/Manager only (BL-7).
        if kind == Payment.Kind.REFUND:
            if actor.role not in REFUND_ROLES:
                raise RefundNotPermittedError(
                    "Only a Manager or Owner may record a refund."
                )
            if amount > REFUND_MANAGER_CEILING and actor.role != Role.OWNER:
                raise OwnerApprovalRequiredError(
                    "Refunds above 5000 require the Owner."
                )
        elif actor.role not in PAYMENT_WRITE_ROLES:
            raise RefundNotPermittedError(
                "Only Owner, Manager or Receptionist may record payments."
            )

        # BL-10: reference required for non-cash methods and for all refunds.
        if (method != Payment.Method.CASH or kind == Payment.Kind.REFUND) and (
            not reference
        ):
            raise ReferenceRequiredError(
                "A reference is required for non-cash payments and all refunds."
            )

        paid_sum, refund_sum = _payment_aggregates(invoice)

        # BL-7 guards against the aggregates BEFORE the insert.
        if kind == Payment.Kind.PAYMENT:
            if paid_sum - refund_sum + amount > invoice.total:
                raise OverpaymentError("Payment would exceed the invoice total.")
        else:
            if refund_sum + amount > paid_sum:
                raise RefundExceedsPaymentsError(
                    "Refund would exceed recorded payments."
                )

        payload_hash = hashlib.sha256(
            _canonical_payment_payload(
                invoice_id=invoice.id,
                kind=kind,
                method=method,
                amount=amount,
                reference=reference,
            ).encode("utf-8")
        ).hexdigest()

        with transaction.atomic():
            existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                if existing.payload_sha256 != payload_hash:
                    raise IdempotencyKeyReusedError(
                        "Idempotency key was already used with a different payload."
                    )
                return existing, False

            try:
                with transaction.atomic():
                    payment = Payment.objects.create(
                        invoice=invoice,
                        kind=kind,
                        method=method,
                        amount=amount,
                        received_by=actor,
                        reference=reference,
                        idempotency_key=idempotency_key,
                        payload_sha256=payload_hash,
                    )
                    # BL-6: recompute status in the SAME transaction as the insert.
                    new_paid = (
                        paid_sum + amount if kind == Payment.Kind.PAYMENT else paid_sum
                    )
                    new_refund = (
                        refund_sum + amount
                        if kind == Payment.Kind.REFUND
                        else refund_sum
                    )
                    new_status = _derive_invoice_status(
                        total=invoice.total,
                        paid_sum=new_paid,
                        refund_sum=new_refund,
                    )
                    old_status: str | None = None
                    if new_status != invoice.status:
                        old_status = invoice.status
                        invoice.status = new_status
                        invoice.save(update_fields=["status", "updated_at"])
            except IntegrityError:
                # Concurrent record with the same key: fall back to replay path.
                existing = Payment.objects.filter(
                    idempotency_key=idempotency_key
                ).first()
                if existing is None:
                    raise
                if existing.payload_sha256 != payload_hash:
                    raise IdempotencyKeyReusedError(
                        "Idempotency key was already used with a different payload."
                    ) from None
                return existing, False

            # LAB-40 (KAN-165): Synchronous revenue-share ledger consumer
            # (Doc 05 §6.2). Called after payment insert, before commit, in the
            # same transaction. If the consumer raises, the whole payment
            # transaction rolls back — no half-state.
            is_refund = kind == Payment.Kind.REFUND
            from apps.partners.services import record_reversal, record_share_entry

            if is_refund:
                record_reversal(payment)
            else:
                record_share_entry(payment)

            # Audit: immutable row in the same transaction (BL-V3: actor recorded).
            # The billing.payment_recorded event rides on the audit row until the
            # event bus lands; refunds additionally flag the Doc 05 share-reversal
            # hook (BL-7: the ledger write itself is Doc 05's).
            after: dict[str, Any] = {
                "event": "billing.payment_recorded",
                "kind": kind,
                "invoice_id": str(invoice.id),
                "method": method,
                "amount": f"{amount:.2f}",
                "reference": reference,
                "received_by": str(actor.id),
                "idempotency_key": idempotency_key,
                "invoice_status": {"from": old_status, "to": new_status},
            }
            if is_refund:
                after["doc05_share_reversal_hook"] = True
            AuditLog.objects.create(
                actor_id=actor.id,
                action="payment.refunded" if is_refund else "payment.recorded",
                entity_type="payment",
                entity_id=payment.id,
                before_jsonb=None,
                after_jsonb=after,
                ip=ip,
                user_agent=user_agent,
            )
            return payment, True


# ---------------------------------------------------------------------------
# LAB-20 — Invoice cancel + reads (original LAB-22, Doc 03 §5.3 BL-8, §6.4)
# ---------------------------------------------------------------------------

LIST_DEFAULT_LIMIT = 50
LIST_MAX_LIMIT = 200


def _encode_cursor(created_at: datetime, invoice_id: uuid.UUID) -> str:
    """Opaque cursor: base64url JSON of the last row's (created_at, id)."""
    payload = {"created_at": created_at.isoformat(), "id": str(invoice_id)}
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode a cursor; raises InvalidFilterError on any malformed input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        payload = json.loads(raw)
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        invoice_id = uuid.UUID(str(payload["id"]))
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise InvalidFilterError("Invalid cursor.") from exc
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at, invoice_id


class InvoiceQueryService:
    """Read + cancel operations on invoices (LAB-20, original LAB-22)."""

    __test__ = False

    @staticmethod
    def list_invoices(
        *,
        actor: StaffUser,
        status: str | None = None,
        patient_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = LIST_DEFAULT_LIMIT,
    ) -> tuple[list[Invoice], str | None]:
        """Cursor-paginated invoice list (Doc 03 §6.1).

        Stable ordering: created_at DESC, id DESC. Returns (rows, next_cursor).
        Unknown enum filter values → 422 (InvalidFilterError).

        Branch scope (Doc 04 §8.5 Layer 2): the base queryset is
        ``Invoice.objects.scoped_to(actor)`` — a scoped caller sees only
        their assigned branches; an out-of-scope ``branch_id`` filter
        therefore yields no rows.
        """
        qs = Invoice.objects.scoped_to(actor).order_by("-created_at", "-id")
        if status is not None:
            if status not in Invoice.Status.values:
                raise InvalidFilterError(f"Unknown status filter: {status}.")
            qs = qs.filter(status=status)
        if patient_id is not None:
            qs = qs.filter(patient_id=patient_id)
        if branch_id is not None:
            qs = qs.filter(branch_id=branch_id)
        if created_after is not None:
            qs = qs.filter(created_at__gte=created_after)
        if created_before is not None:
            qs = qs.filter(created_at__lte=created_before)
        if cursor is not None:
            c_created, c_id = _decode_cursor(cursor)
            qs = qs.filter(
                Q(created_at__lt=c_created) | Q(created_at=c_created, id__lt=c_id)
            )
        limit = max(1, min(limit, LIST_MAX_LIMIT))
        rows = list(qs[: limit + 1])
        next_cursor: str | None = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = _encode_cursor(last.created_at, last.id)
            rows = rows[:limit]
        return rows, next_cursor

    @staticmethod
    def get_invoice_detail(
        *, invoice_id: uuid.UUID, actor: StaffUser
    ) -> dict[str, Any]:
        """Invoice + items + payments + computed net_paid (read-only).

        Branch scope (Doc 04 §8.5 Layer 2): fetched through the scoped
        queryset, so an out-of-scope invoice is simply not found → 404
        (Doc 03 P-7 anti-oracle), indistinguishable from a missing one.
        """
        try:
            invoice = (
                Invoice.objects.scoped_to(actor)
                .prefetch_related("items", "payments")
                .get(pk=invoice_id)
            )
        except (Invoice.DoesNotExist, ValidationError):
            raise BillingNotFoundError("Invoice not found.") from None
        agg = invoice.payments.aggregate(
            paid=Sum("amount", filter=Q(kind=Payment.Kind.PAYMENT)),
            refunded=Sum("amount", filter=Q(kind=Payment.Kind.REFUND)),
        )
        net_paid = (agg["paid"] or Decimal("0.00")) - (
            agg["refunded"] or Decimal("0.00")
        )
        return {"invoice": invoice, "net_paid": net_paid}

    @staticmethod
    def cancel_invoice(
        *,
        invoice_id: uuid.UUID,
        reason: str | None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Invoice:
        """Cancel an invoice (BL-8).

        Allowed only while status = unpaid AND no (non-cancelled) sample has
        been collected against it. Otherwise 409 invalid_state_transition.
        Cancel is a status change + audit row, never a delete. Repeat cancel
        on an already-cancelled invoice → 409 (state guard, no double effect).
        """
        if not reason or not reason.strip():
            raise CancelReasonRequiredError(
                "A reason is required to cancel an invoice."
            )
        with transaction.atomic():
            try:
                # Layer 2 (Doc 04 §8.5): scoped fetch — out-of-scope -> 404.
                invoice = (
                    Invoice.objects.scoped_to(actor)
                    .select_for_update()
                    .get(pk=invoice_id)
                )
            except (Invoice.DoesNotExist, ValidationError):
                raise BillingNotFoundError("Invoice not found.") from None
            if invoice.status != Invoice.Status.UNPAID:
                raise InvalidStateTransitionError(
                    "Only unpaid invoices can be cancelled."
                )
            collected = (
                Sample.objects.filter(invoice=invoice)
                .exclude(status=Sample.Status.CANCELLED)
                .exists()
            )
            if collected:
                raise InvalidStateTransitionError(
                    "Cannot cancel: a sample has already been collected "
                    "against this invoice."
                )
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=["status", "updated_at"])
            AuditLog.objects.create(
                actor_id=actor.id,
                action="invoice.cancelled",
                entity_type="invoice",
                entity_id=invoice.id,
                before_jsonb={"status": Invoice.Status.UNPAID.value},
                after_jsonb={
                    "event": "invoice.cancelled",
                    "status": Invoice.Status.CANCELLED.value,
                    "reason": reason.strip(),
                },
                ip=ip,
                user_agent=user_agent,
            )
            return invoice
