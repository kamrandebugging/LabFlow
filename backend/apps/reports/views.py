"""DRF views for Reports — async PDF pipeline (Doc 03 §5.6 RP-1/RP-2/RP-3,
§6.7, §10; KAN-155 / LAB-30, original LAB-35 + LAB-43) and the public
report portal: access-token mint / redeem / revoke (Doc 03 §5.6 RP-8/RP-9,
RP-V2/RP-V3, §6.7, §6.8; KAN-156 / LAB-31, original LAB-36).

POST /api/v1/reports/{id}/regenerate — roles Owner, Manager, Pathologist
(exact §6.6/§6.7 roles cell: "O M P").
POST /api/v1/reports/{id}/access-token — roles O M R (§6.7).
POST /api/v1/reports/{id}/revoke-token — roles O M (§6.7).
GET  /api/v1/report-access/{token} — PUBLIC, no auth; the token is the
  only credential (RP-V3).
GET  /api/v1/report-files/<sig>/ — PUBLIC short-lived signed download
  target for the 302 (dev/test path; R2/MinIO pre-signed URLs in prod).

Thin views: all business logic lives in ReportService/ReportAccessService.
"""

from typing import Any, cast

from django.core.signing import BadSignature, TimestampSigner
from django.http import FileResponse, HttpResponse
from django.utils.html import escape
from rest_framework import permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.reports.models import ReportVersion
from apps.reports.serializers import ReportDeliverSerializer, TokenRevokeSerializer
from apps.reports.services import (
    FILE_URL_VALIDITY_SECONDS,
    REPORT_ACCESS_TOKEN_ROLES,
    REPORT_DELIVER_ROLES,
    REPORT_REGENERATE_ROLES,
    REPORT_REVOKE_TOKEN_ROLES,
    ReportAccessService,
    ReportDeliveryService,
    ReportError,
    ReportService,
)
from apps.reports.storage import REPORT_FILE_SIGNER_SALT, ReportStorage
from apps.reports.throttling import get_client_ip, public_rate_limit_exceeded


def _format_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


class ReportRegenerateView(APIView):
    """POST /api/v1/reports/{id}/regenerate — enqueue a new PDF version."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, report_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in REPORT_REGENERATE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only the Owner, a Manager or a Pathologist "
                    "may regenerate reports.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            payload = ReportService.regenerate_report(
                report_id=report_id,
                actor=user,
                ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ReportError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_202_ACCEPTED)


def _validate(
    serializer: serializers.Serializer,
) -> tuple[dict[str, Any] | None, Response | None]:
    """Run a serializer; return (data, None) or (None, 422 response)."""
    if not serializer.is_valid():
        first = next(iter(serializer.errors.values()))
        msg = first[0] if isinstance(first, list) else str(first)
        return None, Response(
            _format_error("validation_error", str(msg)),
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return serializer.validated_data, None


class ReportAccessTokenIssueView(APIView):
    """POST /api/v1/reports/{id}/access-token — mint a fresh patient link
    without sending (phone read-out / manual WhatsApp). Roles O M R."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, report_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in REPORT_ACCESS_TOKEN_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only the Owner, a Manager or a Receptionist "
                    "may issue patient report links.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            payload = ReportAccessService.issue_access_token(
                report_id=report_id,
                actor=user,
                ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ReportError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class ReportAccessTokenRevokeView(APIView):
    """POST /api/v1/reports/{id}/revoke-token — revoke one token row or all
    live tokens of the report. Roles O M. Idempotent -> 200."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, report_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in REPORT_REVOKE_TOKEN_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only the Owner or a Manager may revoke patient report links.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        data, err = _validate(TokenRevokeSerializer(data=request.data))
        if err is not None:
            return err
        assert data is not None
        try:
            payload = ReportAccessService.revoke_access_token(
                report_id=report_id,
                actor=user,
                token_id=data.get("token_id"),
                revoke_all=data.get("all", False),
                ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ReportError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_200_OK)


def _link_expired_page(phone: str | None) -> HttpResponse:
    """RP-9: plain 'link expired' page — never a login wall, never the PDF.

    The presented token is never echoed back into the page.
    """
    contact = (
        f"Please call the laboratory at {escape(phone)} to request a new link."
        if phone
        else "Please contact the laboratory to request a new link."
    )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>Report link expired</title></head><body>"
        "<h1>This report link has expired</h1>"
        "<p>For your privacy, report links stop working after their "
        "validity period or when the laboratory revokes them.</p>"
        f"<p>{contact}</p>"
        "</body></html>"
    )
    return HttpResponse(html, status=410, content_type="text/html")


class ReportAccessView(APIView):
    """GET /api/v1/report-access/{token} — PUBLIC patient endpoint.

    No authentication: the token is the ONLY credential (RP-V3). Throttled
    per IP before the argon2 scan. Unknown -> 404 JSON; expired/revoked ->
    410 HTML page with the lab's phone (RP-9); success -> 302 to a
    short-lived signed storage URL.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request: Request, token: str) -> Response | HttpResponse:
        if public_rate_limit_exceeded(request, scope="report_access"):
            return Response(
                _format_error(
                    "rate_limited",
                    "Too many requests. Please try again in a minute.",
                ),
                status=429,
            )
        try:
            payload = ReportAccessService.redeem_access_token(
                token=token,
                ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ReportError as exc:
            if exc.status_code == 410:
                phone = (
                    exc.details.get("phone") if isinstance(exc.details, dict) else None
                )
                return _link_expired_page(phone)
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        response = HttpResponse(status=302)
        response["Location"] = payload["redirect_url"]
        # The signed file URL is short-lived: never let a browser/proxy
        # cache the 302, or a reopened link would replay an expired URL.
        response["Cache-Control"] = "no-store"
        return response


class ReportFileDownloadView(APIView):
    """GET /api/v1/report-files/<sig>/ — PUBLIC short-lived download.

    Dev/test path for the 302 target (prod uses R2/MinIO pre-signed URLs
    directly). The TimestampSigner signature is verified (max age
    FILE_URL_VALIDITY_SECONDS) AND the tenant-scoped report_version row for
    the pdf_key must exist before streaming. Throttled per IP like the
    access endpoint.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request: Request, signed: str) -> Response | FileResponse:
        if public_rate_limit_exceeded(request, scope="report_file"):
            return Response(
                _format_error(
                    "rate_limited",
                    "Too many requests. Please try again in a minute.",
                ),
                status=429,
            )
        try:
            pdf_key = TimestampSigner(salt=REPORT_FILE_SIGNER_SALT).unsign(
                signed, max_age=FILE_URL_VALIDITY_SECONDS
            )
        except BadSignature:
            return Response(
                _format_error("file_not_found", "File not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        if not ReportVersion.objects.filter(pdf_key=pdf_key).exists():
            return Response(
                _format_error("file_not_found", "File not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        storage = ReportStorage()
        if not storage.pdf_exists(pdf_key):
            return Response(
                _format_error("file_not_found", "File not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        filename = pdf_key.rsplit("/", 1)[-1]
        response = FileResponse(
            storage.open_pdf(pdf_key),
            content_type="application/pdf",
            filename=filename,
            as_attachment=False,
        )
        response["Cache-Control"] = "no-store"
        return response


class ReportDeliverView(APIView):
    """POST /api/v1/reports/{id}/deliver — dispatch a report link (§6.7).

    Roles O M R. Creates the PENDING report_delivery row, mints an access
    token (the plain link is returned once in the 202 as a staff fallback),
    enqueues reports.deliver. -> 202 with the delivery row; a second call
    for the same channel + contact within 10 minutes -> 200 with the
    existing PENDING delivery. Thin view: logic in ReportDeliveryService.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, report_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in REPORT_DELIVER_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only the Owner, a Manager or a Receptionist may deliver reports.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        data, err = _validate(ReportDeliverSerializer(data=request.data))
        if err is not None:
            return err
        assert data is not None
        try:
            payload = ReportDeliveryService.deliver_report(
                report_id=report_id,
                channel=data["channel"],
                contact_id=data["contact_id"],
                actor=user,
                ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ReportError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        delivery = payload["delivery"]
        body: dict[str, Any] = {
            "id": str(delivery.id),
            "report_id": str(delivery.report_id),
            "channel": delivery.channel,
            "contact_id": str(delivery.contact_id),
            "status": delivery.status,
            "created_at": delivery.created_at.isoformat(),
        }
        if payload["deduplicated"]:
            return Response(body, status=status.HTTP_200_OK)
        body["token_id"] = payload["token_id"]
        body["link"] = payload["link"]
        return Response(body, status=status.HTTP_202_ACCEPTED)
