"""DRF views for Billing — invoice creation + payments (Doc 03 §5.3, §6.4,
KAN-124 / LAB-18, KAN-130 / LAB-19).

POST /api/v1/invoices — roles Owner, Manager, Receptionist.
POST /api/v1/invoices/{id}/payments — roles Owner, Manager, Receptionist
(refunds: Owner, Manager only).
Thin views: all business logic lives in BillingService / PaymentService.
"""

from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.billing.serializers import (
    InvoiceCreateSerializer,
    InvoiceSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
)
from apps.billing.services import (
    BILLING_WRITE_ROLES,
    PAYMENT_WRITE_ROLES,
    BillingError,
    BillingService,
    PaymentService,
)
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


class InvoiceCreateView(APIView):
    """POST /api/v1/invoices — create an invoice (BL-1..BL-4, BL-6, BL-V1..BL-V3)."""

    permission_classes = [permissions.IsAuthenticated]

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
    """POST /api/v1/invoices/{id}/payments — record payment/refund."""

    permission_classes = [permissions.IsAuthenticated]

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
