"""DRF views for Reports — async PDF pipeline (Doc 03 §5.6 RP-1/RP-2/RP-3,
§6.7, §10; KAN-155 / LAB-30, original LAB-35 + LAB-43).

POST /api/v1/reports/{id}/regenerate — roles Owner, Manager, Pathologist
(exact §6.6/§6.7 roles cell: "O M P").

Thin views: all business logic lives in ReportService.
"""

from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.reports.services import (
    REPORT_REGENERATE_ROLES,
    ReportError,
    ReportService,
)


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
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ReportError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_202_ACCEPTED)
