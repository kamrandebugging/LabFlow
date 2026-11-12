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
from datetime import UTC, datetime
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
from apps.billing.models import Invoice, Payment
from apps.billing.serializers import (
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
    PAYMENT_WRITE_ROLES,
    BillingError,
    BillingService,
    InvalidFilterError,
    InvoiceQueryService,
    PaymentService,
)
from apps.branches.scope_views import BranchScopedAPIView, IsInBranchScope
from apps.catalog.services import TestNotPricedError


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
        today_total = (
            Invoice.objects.scoped_to(user)
            .filter(created_at__date=today)
            .exclude(status=Invoice.Status.CANCELLED)
            .aggregate(sum=Sum("total"))["sum"]
        ) or Decimal("0.00")
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
            "status": invoice.status,
            "subtotal": invoice.subtotal,
            "discount_amount": invoice.discount_amount,
            "discount_reason": invoice.discount_reason,
            "total": invoice.total,
            "items": list(invoice.items.all()),
            "payments": list(invoice.payments.all()),
            "net_paid": detail["net_paid"],
            "created_at": invoice.created_at,
        }
        return Response(
            InvoiceDetailSerializer(payload, context={"request": request}).data,
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
