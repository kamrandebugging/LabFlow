"""DRF views for Billing — invoice create/read/cancel + payments (Doc 03 §5.3,
§6.4, KAN-124 / LAB-18, KAN-130 / LAB-19, KAN-132 / LAB-20).

POST /api/v1/invoices — roles Owner, Manager, Receptionist.
GET /api/v1/invoices — roles Owner, Manager, Receptionist, Technician,
Pathologist (cursor-paginated).
GET /api/v1/invoices/{id} — same read roles.
POST /api/v1/invoices/{id}/cancel — roles Owner, Manager, Receptionist.
POST /api/v1/invoices/{id}/payments — roles Owner, Manager, Receptionist
(refunds: Owner, Manager only).
Thin views: all business logic lives in BillingService / PaymentService /
InvoiceQueryService.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from django.db.models import Sum, TextField
from django.db.models.functions import Cast
from django.http import QueryDict
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.billing.models import CreditNote, Invoice, Payment
from apps.billing.serializers import (
    CreditNoteCreateSerializer,
    CreditNoteSerializer,
    CreditNoteVoidSerializer,
    DayCloseCreateSerializer,
    DayCloseSummarySerializer,
    InvoiceCancelSerializer,
    InvoiceCreateSerializer,
    InvoiceDetailSerializer,
    InvoiceSerializer,
    InvoiceSummarySerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
)
from apps.billing.services import (
    BILLING_READ_ROLES,
    BILLING_WRITE_ROLES,
    CREDIT_NOTE_ROLES,
    DAY_CLOSE_ROLES,
    PAYMENT_WRITE_ROLES,
    BillingError,
    BillingService,
    CreditNoteService,
    DayCloseService,
    InvalidFilterError,
    InvoiceQueryService,
    PaymentService,
)
from apps.branches.scope_views import BranchScopedAPIView, IsInBranchScope
from apps.catalog.services import TestNotPricedError
from apps.core.authorization import OWNER_ONLY


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _format_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


class InvoiceCollectionView(BranchScopedAPIView):
    """GET /api/v1/invoices — cursor-paginated list (Doc 03 §6.1).

    POST /api/v1/invoices — create an invoice (BL-1..BL-4, BL-6, BL-V1..BL-V3).

    Branch scope (Doc 04 §8.5): the list is scoped to the caller's
    assignments in InvoiceQueryService (Layer 2); IsInBranchScope re-checks
    the body's branch_id on create (Layer 3).
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = "body:branch_id"

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BILLING_READ_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only staff may list invoices.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            filters = _parse_list_params(request.query_params)
            rows, next_cursor = InvoiceQueryService.list_invoices(actor=user, **filters)
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        today = timezone.localdate()
        today_qs = (
            Invoice.objects.scoped_to(user)
            .filter(created_at__date=today)
            .exclude(status=Invoice.Status.CANCELLED)
        )
        billed = today_qs.aggregate(sum=Sum("total"))["sum"] or Decimal("0.00")
        refunded = Payment.objects.filter(
            invoice__in=today_qs, kind=Payment.Kind.REFUND
        ).aggregate(sum=Sum("amount"))["sum"] or Decimal("0.00")
        credited = CreditNote.objects.filter(
            invoice__in=today_qs, voided_at__isnull=True
        ).aggregate(sum=Sum("amount"))["sum"] or Decimal("0.00")
        # Net revenue = billed − refunds − credit notes (never client-computed).
        today_total = billed - refunded - credited
        body = {
            "results": InvoiceSummarySerializer(rows, many=True).data,
            "next_cursor": next_cursor,
            "daily_total": f"{today_total:.2f}",
        }
        return Response(body, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BILLING_WRITE_ROLES:
            return Response(
                _format_error(
                    "forbidden", "Only Owner, Manager or Receptionist may invoice."
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not idempotency_key:
            return Response(
                _format_error(
                    "idempotency_key_required",
                    "The Idempotency-Key header is required.",
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        serializer = InvoiceCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            amount_err = str(err_dict.get("discount_amount", ""))
            if (
                "Amount must be a string" in amount_err
                or "max_two_decimals" in amount_err
            ):
                return Response(
                    _format_error(
                        "money_must_be_string",
                        "Discount must be a string, max 2 decimals.",
                        err_dict,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            invoice, created = BillingService.create_invoice(
                patient_id=data["patient_id"],
                branch_id=data["branch_id"],
                referral_partner_id=data.get("referral_partner_id"),
                items=data["items"],
                discount_amount=data["discount_amount"],
                discount_reason=data.get("discount_reason"),
                idempotency_key=idempotency_key,
                actor=user,
                ip=ip,
                user_agent=user_agent,
            )
        except TestNotPricedError as exc:
            return Response(
                _format_error("test_not_priced", str(exc)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )

        body = InvoiceSerializer(invoice).data
        return Response(
            body,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaymentCreateView(APIView):
    """POST /api/v1/invoices/{id}/payments — record payment/refund.

    Branch scope (Doc 04 §8.5 Layer 3): no branch travels in the body (the
    invoice carries it), so only the zero-assignment gate applies — BS-2.
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = None

    def post(self, request: Request, invoice_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in PAYMENT_WRITE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only Owner, Manager or Receptionist may record payments.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not idempotency_key:
            return Response(
                _format_error(
                    "idempotency_key_required",
                    "The Idempotency-Key header is required.",
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        serializer = PaymentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            amount_err = str(err_dict.get("amount", ""))
            if (
                "Amount must be a string" in amount_err
                or "max_two_decimals" in amount_err
            ):
                return Response(
                    _format_error(
                        "money_must_be_string",
                        "Amount must be a string, max 2 decimals.",
                        err_dict,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # LAB-49 Phase 2.8: a refund needs fresh TOTP proof.
        if data["kind"] == Payment.Kind.REFUND:
            from apps.accounts.step_up import enforce_step_up

            enforce_step_up(user, request, action="a refund")

        try:
            payment, created = PaymentService.record_payment(
                invoice_id=invoice_id,
                kind=data["kind"],
                method=data["method"],
                amount=data["amount"],
                reference=data.get("reference"),
                refund_reason=data.get("refund_reason"),
                idempotency_key=idempotency_key,
                actor=user,
                ip=ip,
                user_agent=user_agent,
            )
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )

        body = PaymentSerializer(payment).data
        return Response(
            body,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _parse_uuid_param(value: Any, field: str) -> uuid.UUID | None:
    """Parse a UUID query param; invalid → 422 invalid_filter (raised)."""
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise InvalidFilterError(f"Invalid {field}.") from None


def _parse_datetime_param(value: Any, field: str) -> datetime | None:
    """Parse an ISO 8601 query param; invalid → 422 invalid_filter (raised)."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        raise InvalidFilterError(f"Invalid {field}; expected ISO 8601.") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_list_params(params: QueryDict) -> dict[str, Any]:
    """Translate GET /invoices query params to InvoiceQueryService kwargs.

    Unknown filter parameters are ignored (Doc 03 §6.1).
    """
    filters: dict[str, Any] = {}
    status_val = params.get("status")
    if status_val is not None:
        filters["status"] = status_val
    patient_id = _parse_uuid_param(params.get("patient_id"), "patient_id")
    if patient_id is not None:
        filters["patient_id"] = patient_id
    branch_id = _parse_uuid_param(params.get("branch_id"), "branch_id")
    if branch_id is not None:
        filters["branch_id"] = branch_id
    created_after = _parse_datetime_param(params.get("created_after"), "created_after")
    if created_after is not None:
        filters["created_after"] = created_after
    created_before = _parse_datetime_param(
        params.get("created_before"), "created_before"
    )
    if created_before is not None:
        filters["created_before"] = created_before
    raw_cursor = params.get("cursor")
    if raw_cursor is not None:
        filters["cursor"] = raw_cursor
    raw_limit = params.get("limit")
    if raw_limit is not None:
        try:
            filters["limit"] = int(raw_limit)
        except (ValueError, TypeError):
            raise InvalidFilterError("Invalid limit.") from None
    return filters


def _parse_path_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _invoice_number(invoice_id: uuid.UUID) -> str:
    """Human-readable invoice number derived from the stored UUID."""
    return f"INV-{str(invoice_id)[:8].upper()}"


def _resolve_invoice_reference(user: StaffUser, value: Any) -> uuid.UUID | None:
    """Resolve a UUID or an ``INV-XXXXXXXX`` number to the invoice UUID.

    The invoice model has no separate number column; the UI's number is the
    first eight characters of the UUID prefixed with ``INV-``. Numbers are
    resolved through the caller's branch scope, so out-of-scope invoices stay
    indistinguishable from missing ones.
    """
    direct = _parse_path_uuid(value)
    if direct is not None:
        return direct
    raw = str(value or "").strip()
    if not raw:
        return None
    prefix = raw[4:] if raw.upper().startswith("INV-") else raw
    prefix = prefix.strip().lower()
    if len(prefix) < 8 or any(ch not in "0123456789abcdef" for ch in prefix):
        return None
    match = (
        Invoice.objects.scoped_to(user)
        .annotate(id_text=Cast("id", output_field=TextField()))
        .filter(id_text__istartswith=prefix)
        .order_by("-created_at")
        .first()
    )
    return match.id if match is not None else None


class InvoiceDetailView(APIView):
    """GET /api/v1/invoices/{id} — detail with items, payments, net_paid."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, invoice_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BILLING_READ_ROLES:
            return Response(
                _format_error("forbidden", "Only staff may view invoices."),
                status=status.HTTP_403_FORBIDDEN,
            )
        iid = _resolve_invoice_reference(user, invoice_id)
        if iid is None:
            return Response(
                _format_error("not_found", "Invoice not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            detail = InvoiceQueryService.get_invoice_detail(invoice_id=iid, actor=user)
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        invoice = detail["invoice"]
        patient = invoice.patient
        dob = patient.date_of_birth
        age_display: str | None = None
        if dob is not None:
            today = timezone.localdate()
            years = (
                today.year
                - dob.year
                - ((today.month, today.day) < (dob.month, dob.day))
            )
            age_display = f"{years}y"
        payload: dict[str, Any] = {
            "id": invoice.id,
            "invoice_number": _invoice_number(invoice.id),
            "patient_id": invoice.patient_id,
            "patient_name": patient.name,
            "patient_mrn": patient.mrn,
            "patient_sex": patient.sex,
            "patient_age": age_display,
            "patient_phone": patient.phone,
            "branch_id": invoice.branch_id,
            "branch_name": invoice.branch.name,
            "referral_partner_id": invoice.referral_partner_id,
            "referral_partner_name": getattr(invoice.referral_partner, "name", None),
            "status": invoice.status,
            "subtotal": invoice.subtotal,
            "discount_amount": invoice.discount_amount,
            "discount_reason": invoice.discount_reason,
            "total": invoice.total,
            "items": list(invoice.items.all()),
            "payments": list(invoice.payments.all()),
            "credit_notes": list(
                invoice.credit_notes.select_related("issued_by", "voided_by").order_by(
                    "issued_at"
                )
            ),
            "net_paid": detail["net_paid"],
            "net_revenue": detail["net_revenue"],
            "created_at": invoice.created_at,
        }
        return Response(
            InvoiceDetailSerializer(payload, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class InvoiceHistoryView(APIView):
    """GET /api/v1/invoices/{id}/history — read-only append-only event trail.

    Derives created / payment / refund / cancel / discount events from the
    immutable Payment rows, the invoice row and its AuditLog entries. No
    write method exists: history rows can never be edited or deleted.
    Same read roles and branch scoping as InvoiceDetailView.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, invoice_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BILLING_READ_ROLES:
            return Response(
                _format_error("forbidden", "Only staff may view invoices."),
                status=status.HTTP_403_FORBIDDEN,
            )
        iid = _resolve_invoice_reference(user, invoice_id)
        if iid is None:
            return Response(
                _format_error("not_found", "Invoice not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            detail = InvoiceQueryService.get_invoice_detail(invoice_id=iid, actor=user)
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        invoice = detail["invoice"]

        from apps.accounts.models import AuditLog
        from apps.accounts.models import StaffUser as _Staff

        events: list[dict[str, Any]] = []

        # Actor names for audit rows (actor_id is a plain UUID, no FK).
        audit_rows = list(
            AuditLog.objects.filter(
                entity_type="invoice", entity_id=invoice.id
            ).order_by("at")
        )
        actor_ids: set[uuid.UUID] = set()
        for row in audit_rows:
            if row.actor_id is not None:
                actor_ids.add(row.actor_id)
        payment_rows = list(
            invoice.payments.all().select_related("received_by").order_by("created_at")
        )
        for p in payment_rows:
            if p.received_by_id is not None:
                actor_ids.add(p.received_by_id)
        credit_notes = list(
            invoice.credit_notes.all()
            .select_related("issued_by", "voided_by")
            .order_by("issued_at")
        )
        for cn in credit_notes:
            if cn.issued_by_id is not None:
                actor_ids.add(cn.issued_by_id)
            if cn.voided_by_id is not None:
                actor_ids.add(cn.voided_by_id)
        names: dict[Any, str] = {}
        if actor_ids:
            for s in _Staff.objects.filter(id__in=actor_ids):
                names[s.id] = getattr(s, "name", None) or s.email

        # created (+ discount applied at creation)
        created_row = next(
            (r for r in audit_rows if r.action == "invoice.created"), None
        )
        created_at = created_row.at if created_row else invoice.created_at
        created_actor = names.get(created_row.actor_id) if created_row else None
        events.append(
            {
                "event": "created",
                "at": created_at.isoformat(),
                "actor": created_actor,
                "amount": f"{invoice.total:.2f}",
                "referral_partner": getattr(invoice.referral_partner, "name", None),
            }
        )
        if invoice.discount_amount > Decimal("0.00"):
            events.append(
                {
                    "event": "discount",
                    "at": created_at.isoformat(),
                    "actor": created_actor,
                    "amount": f"{invoice.discount_amount:.2f}",
                    "reason": invoice.discount_reason,
                }
            )

        # payment / refund rows (append-only financial facts)
        for p in payment_rows:
            ev: dict[str, Any] = {
                "event": "refund" if p.kind == Payment.Kind.REFUND else "payment",
                "at": p.created_at.isoformat(),
                "actor": names.get(p.received_by_id),
                "amount": f"{p.amount:.2f}",
            }
            if p.kind == Payment.Kind.REFUND:
                ev["reason"] = p.refund_reason or p.reference
            events.append(ev)

        # credit notes (append-only reversal documents)
        for cn in credit_notes:
            events.append(
                {
                    "event": "credit_note",
                    "at": cn.issued_at.isoformat(),
                    "actor": names.get(cn.issued_by_id),
                    "amount": f"{cn.amount:.2f}",
                    "reason": cn.reason,
                    "number": cn.number,
                    "method": cn.method,
                    "voided": cn.voided_at is not None,
                }
            )
            if cn.voided_at is not None:
                events.append(
                    {
                        "event": "credit_note_voided",
                        "at": cn.voided_at.isoformat(),
                        "actor": names.get(cn.voided_by_id),
                        "amount": f"{cn.amount:.2f}",
                        "reason": cn.void_reason,
                        "number": cn.number,
                    }
                )

        # cancel
        for row in audit_rows:
            if row.action == "invoice.cancelled":
                after = row.after_jsonb or {}
                events.append(
                    {
                        "event": "cancel",
                        "at": row.at.isoformat(),
                        "actor": names.get(row.actor_id),
                        "amount": None,
                        "reason": after.get("reason"),
                    }
                )

        events.sort(key=lambda e: e["at"])
        return Response(
            {"invoice_id": str(invoice.id), "events": events},
            status=status.HTTP_200_OK,
        )


class InvoiceCancelView(APIView):
    """POST /api/v1/invoices/{id}/cancel — cancel an unpaid invoice (BL-8).

    Branch scope (Doc 04 §8.5 Layer 3): no branch travels in the body (the
    invoice carries it), so only the zero-assignment gate applies — BS-2.
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = None

    def post(self, request: Request, invoice_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BILLING_WRITE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only Owner, Manager or Receptionist may cancel invoices.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        iid = _parse_path_uuid(invoice_id)
        if iid is None:
            return Response(
                _format_error("not_found", "Invoice not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = InvoiceCancelSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            if "reason" in err_dict:
                return Response(
                    _format_error(
                        "cancel_reason_required",
                        "A reason is required to cancel an invoice.",
                        err_dict,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        try:
            invoice = InvoiceQueryService.cancel_invoice(
                invoice_id=iid,
                reason=data["reason"],
                actor=user,
                ip=ip,
                user_agent=user_agent,
            )
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_200_OK)


class CreditNoteCreateView(APIView):
    """POST /api/v1/invoices/{id}/credit-notes — reverse a paid invoice.

    Owner/Manager only. Creates an append-only credit-note document; the
    invoice, its items and its payments are never modified.
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = None

    def post(self, request: Request, invoice_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in CREDIT_NOTE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only an Owner or Manager may issue a credit note.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        iid = _parse_path_uuid(invoice_id)
        if iid is None:
            return Response(
                _format_error("not_found", "Invoice not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CreditNoteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            if "reason" in err_dict:
                return Response(
                    _format_error(
                        "credit_note_reason_required",
                        "A reason is required to issue a credit note.",
                        err_dict,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not idempotency_key:
            return Response(
                _format_error(
                    "idempotency_key_required",
                    "An Idempotency-Key header is required.",
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        try:
            note, created = CreditNoteService.issue(
                invoice_id=iid,
                amount=data["amount"],
                reason=data["reason"],
                method=data["method"],
                idempotency_key=idempotency_key,
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(
            CreditNoteSerializer(note).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CreditNoteVoidView(APIView):
    """POST /api/v1/invoices/{id}/credit-notes/{note_id}/void — Owner only.

    Voiding is append-only: the note row and its CN number stay, the void
    stops it counting toward revenue, and the invoice status is re-derived.
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = None

    def post(self, request: Request, invoice_id: Any, note_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in OWNER_ONLY:
            return Response(
                _format_error("forbidden", "Only the Owner may void a credit note."),
                status=status.HTTP_403_FORBIDDEN,
            )
        iid = _parse_path_uuid(invoice_id)
        nid = _parse_path_uuid(note_id)
        if iid is None or nid is None:
            return Response(
                _format_error("not_found", "Credit note not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CreditNoteVoidSerializer(data=request.data)
        if not serializer.is_valid():
            if "reason" in serializer.errors:
                return Response(
                    _format_error(
                        "credit_note_reason_required",
                        "A reason is required to void a credit note.",
                        serializer.errors,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error(
                    "validation_error", "Invalid payload.", serializer.errors
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            note = CreditNoteService.void(
                invoice_id=iid,
                note_id=nid,
                reason=serializer.validated_data["reason"],
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(CreditNoteSerializer(note).data, status=status.HTTP_200_OK)


class DayCloseView(APIView):
    """GET/POST /api/v1/day-close — reconcile and lock one branch-day.

    GET returns the server-computed totals for a day plus the locked record
    when the day is already closed. POST closes the day (Owner/Manager only);
    closing only writes the reconciliation document, never money.
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = None

    @staticmethod
    def _totals_payload(totals: dict[str, Any]) -> dict[str, Any]:
        return {
            "method_totals": totals["method_totals"],
            "total_in": f"{totals['total_in']:.2f}",
            "total_out": f"{totals['total_out']:.2f}",
            "net_total": f"{totals['net_total']:.2f}",
            "total_invoices": totals["total_invoices"],
            "total_discount": f"{totals['total_discount']:.2f}",
            "total_credit_notes": f"{totals['total_credit_notes']:.2f}",
            "expected_cash": f"{totals['expected_cash']:.2f}",
        }

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BILLING_READ_ROLES:
            return Response(
                _format_error("forbidden", "Only staff may read a day close."),
                status=status.HTTP_403_FORBIDDEN,
            )
        branch_raw = request.query_params.get("branch")
        try:
            branch_id = uuid.UUID(str(branch_raw))
        except (ValueError, TypeError, AttributeError):
            return Response(
                _format_error(
                    "validation_error", "A valid branch query parameter is required."
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        date_raw = request.query_params.get("date")
        if date_raw:
            try:
                day = date.fromisoformat(date_raw)
            except ValueError:
                return Response(
                    _format_error(
                        "validation_error", "date must be an ISO date (YYYY-MM-DD)."
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        else:
            day = timezone.localdate()
        try:
            data = DayCloseService.read(actor=user, branch_id=branch_id, day=day)
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        close = data["close"]
        return Response(
            {
                "branch_id": str(branch_id),
                "date": day.isoformat(),
                "closed": data["closed"],
                "totals": self._totals_payload(data["totals"]),
                "close": (
                    DayCloseSummarySerializer(close).data if close is not None else None
                ),
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in DAY_CLOSE_ROLES:
            return Response(
                _format_error("forbidden", "Only an Owner or Manager may close a day."),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = DayCloseCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            if "counted_cash" in err_dict:
                return Response(
                    _format_error(
                        "validation_error",
                        "The cash counted in the drawer is required.",
                        err_dict,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        day = data.get("date") or timezone.localdate()
        try:
            close = DayCloseService.close(
                actor=user,
                branch_id=data["branch_id"],
                day=day,
                counted_cash=data["counted_cash"],
                difference_note=data.get("difference_note"),
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except BillingError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(
            {
                "branch_id": str(close.branch_id),
                "date": close.business_date.isoformat(),
                "closed": True,
                "close": DayCloseSummarySerializer(close).data,
            },
            status=status.HTTP_201_CREATED,
        )
