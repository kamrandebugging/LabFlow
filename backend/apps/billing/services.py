"""Business logic for the Billing module (Doc 03 §5.3, §6.4, KAN-124 / LAB-18).

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
"""

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.billing.models import Invoice, InvoiceItem
from apps.branches.models import Branch
from apps.catalog.models import Panel, Test
from apps.catalog.services import CatalogService
from apps.partners.models import ReferralPartner
from apps.patients.models import Patient

BILLING_WRITE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
DISCOUNT_ROLES = {Role.OWNER, Role.MANAGER}


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
