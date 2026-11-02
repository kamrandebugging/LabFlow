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

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.branches.models import Branch
from apps.catalog.models import Panel, Test
from apps.catalog.services import CatalogService
from apps.partners.models import ReferralPartner
from apps.patients.models import Patient

BILLING_WRITE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
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
            existing = Invoice.objects.filter(idempotency_key=idempotency_key).first()
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
                existing = Invoice.objects.filter(
                    idempotency_key=idempotency_key
                ).first()
                if existing is None:
                    raise
                if existing.payload_sha256 != payload_hash:
                    raise IdempotencyKeyReusedError(
                        "Idempotency key was already used with a different payload."
                    ) from None
                return existing, False

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
            invoice = Invoice.objects.get(pk=invoice_id)
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

            # Audit: immutable row in the same transaction (BL-V3: actor recorded).
            # The billing.payment_recorded event rides on the audit row until the
            # event bus lands; refunds additionally flag the Doc 05 share-reversal
            # hook (BL-7: the ledger write itself is Doc 05's).
            is_refund = kind == Payment.Kind.REFUND
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
