"""LAB-45 (KAN-264): n8n callback ingestion views (Doc 06 §10).

The only endpoints in the LabFlow API that an external service calls.
They live on the tenant subdomain. No JWT, no cookie — the only
credential is the callback key (X-LabFlow-Callback-Key).

Check order per §5.4: path -> key -> tenant -> slug -> row -> state.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
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
from apps.core.throttling import CallbackThrottle

logger = logging.getLogger(__name__)

CALLBACK_KEY_HEADER = "HTTP_X_LABFLOW_CALLBACK_KEY"


def _error_response(exc: CallbackError) -> Response:
    return Response({"error": exc.error_code}, status=exc.status_code)


def _verify_signed_callback(
    request: Request, raw_body: bytes, idempotency_key: str | None
) -> None:
    """Optional HMAC-SHA256 + 5-minute timestamp + replay rejection (SE-43).

    Required when ``N8N_CALLBACK_REQUIRE_SIGNATURE`` is true (production) or
    whenever the caller supplies a signature. The signed payload is
    ``<timestamp>.<raw body>`` so body tampering is covered.
    """
    signature = request.headers.get("X-LabFlow-Signature", "") or ""
    timestamp = request.headers.get("X-LabFlow-Timestamp", "") or ""
    required = bool(getattr(settings, "N8N_CALLBACK_REQUIRE_SIGNATURE", False))
    if not signature and not required:
        return
    if not signature or not timestamp:
        raise CallbackError("signature_required", 401)
    try:
        sent_at = int(timestamp)
    except ValueError:
        raise CallbackError("stale_timestamp", 401) from None
    if abs(int(time.time()) - sent_at) > 300:
        raise CallbackError("stale_timestamp", 401)

    secret = str(getattr(settings, "N8N_CALLBACK_KEY", "") or "")
    if not secret:
        raise CallbackError("callback_not_configured", 503)
    expected = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise CallbackError("invalid_signature", 401)

    # Replay: the same signature (same body + same timestamp) may be seen once.
    nonce = hashlib.sha256(signature.encode()).hexdigest()
    try:
        if not cache.add(f"callback:nonce:{nonce}", "1", timeout=600):
            raise CallbackError("replayed_callback", 409)
    except CallbackError:
        raise
    except Exception:
        # Cache outage: fail closed for signed callbacks.
        raise CallbackError("callback_unavailable", 503) from None


def _raw_body_and_data(request: Request) -> tuple[bytes, dict[str, Any]]:
    raw = getattr(request._request, "body", b"")  # noqa: SLF001 - DRF wrapper
    if not raw:
        return b"", {}
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise CallbackError("invalid_body", 422) from None
    return raw, parsed if isinstance(parsed, dict) else {}


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
    throttle_classes = [CallbackThrottle]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        raw_body, body = _raw_body_and_data(request)
        try:
            _check_key_and_slug(request, body)
            _verify_signed_callback(request, raw_body, body.get("idempotency_key"))
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
    throttle_classes = [CallbackThrottle]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        raw_body, body = _raw_body_and_data(request)
        try:
            _check_key_and_slug(request, body)
            _verify_signed_callback(request, raw_body, body.get("idempotency_key"))
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
    throttle_classes = [CallbackThrottle]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        raw_body, body = _raw_body_and_data(request)
        try:
            _check_key_and_slug(request, body)
            _verify_signed_callback(request, raw_body, body.get("idempotency_key"))
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
