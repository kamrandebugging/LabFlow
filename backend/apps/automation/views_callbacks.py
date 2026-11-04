"""LAB-45 (KAN-264): n8n callback ingestion views (Doc 06 §10).

The only endpoints in the LabFlow API that an external service calls.
They live on the tenant subdomain. No JWT, no cookie — the only
credential is the callback key (X-LabFlow-Callback-Key).

Check order per §5.4: path -> key -> tenant -> slug -> row -> state.
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.automation.services import (
    CallbackError,
    apply_notification_callback,
    apply_report_delivery_callback,
    apply_settlement_callback,
    verify_callback_key,
)

logger = logging.getLogger(__name__)

CALLBACK_KEY_HEADER = "HTTP_X_LABFLOW_CALLBACK_KEY"


def _error_response(exc: CallbackError) -> Response:
    return Response({"error": exc.error_code}, status=exc.status_code)


def _check_key_and_slug(request: Request, body: dict[str, Any]) -> None:
    """Checks 2 and 4 of §5.4 (check 1 is URL routing, check 3 is the
    TenantMainMiddleware)."""
    if not verify_callback_key(request.META.get(CALLBACK_KEY_HEADER) or ""):
        raise CallbackError("unauthorized_callback", 401)
    tenant = getattr(request, "tenant", None)
    tenant_slug = getattr(tenant, "slug", None)
    if body.get("tenant_slug") != tenant_slug:
        logger.warning(
            "webhook callback rejected: tenant_slug_mismatch (body=%r host=%r)",
            body.get("tenant_slug"),
            tenant_slug,
        )
        raise CallbackError("tenant_slug_mismatch", 403)


def _require_fields(body: dict[str, Any], fields: list[str]) -> None:
    missing = [f for f in fields if body.get(f) in (None, "")]
    if missing:
        raise CallbackError("invalid_body", 422, {"missing": missing})


class NotificationCallbackView(APIView):
    """POST /api/v1/webhooks/n8n/notification (Doc 06 §10).

    Callback for a notification row that is not a report delivery and not
    a settlement delivery — in v1, the sample.collected and
    sample.rejected notices.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        try:
            _check_key_and_slug(request, body)
            _require_fields(body, ["event", "tenant_slug", "idempotency_key", "status"])
            result = apply_notification_callback(
                idempotency_key=str(body["idempotency_key"]),
                status=str(body["status"]),
                last_error=body.get("last_error"),
            )
        except CallbackError as exc:
            return _error_response(exc)
        return Response(result, status=200)


class ReportDeliveryCallbackView(APIView):
    """POST /api/v1/webhooks/n8n/report-delivery (Doc 06 §10).

    Callback for a report_delivery row. whatsapp_url is required on a
    SENT callback for the WhatsApp channel. OPENED is never accepted.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        try:
            _check_key_and_slug(request, body)
            _require_fields(
                body,
                ["tenant_slug", "idempotency_key", "channel", "status"],
            )
            result = apply_report_delivery_callback(
                idempotency_key=str(body["idempotency_key"]),
                channel=str(body["channel"]),
                status=str(body["status"]),
                whatsapp_url=body.get("whatsapp_url"),
                last_error=body.get("last_error"),
            )
        except CallbackError as exc:
            return _error_response(exc)
        return Response(result, status=200)


class SettlementDeliveryCallbackView(APIView):
    """POST /api/v1/webhooks/n8n/settlement-delivery (Doc 06 §10).

    Callback for a settlement's notification row (Doc 05 DL-3). On SENT,
    the settlement moves APPROVED -> SENT in the same transaction.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        try:
            _check_key_and_slug(request, body)
            _require_fields(
                body,
                ["settlement_id", "tenant_slug", "idempotency_key", "status"],
            )
            result = apply_settlement_callback(
                settlement_id=str(body["settlement_id"]),
                idempotency_key=str(body["idempotency_key"]),
                status=str(body["status"]),
                last_error=body.get("last_error"),
            )
        except CallbackError as exc:
            return _error_response(exc)
        return Response(result, status=200)
