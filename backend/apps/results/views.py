"""DRF views for Results — batch result entry (Doc 03 §5.5 RS-1/RS-2/RS-3/RS-V2,
§6.6, §8, KAN-150 / LAB-25, original LAB-30), clinical verification
(Doc 03 §5.5 RS-4–RS-10, §6.6, §10, KAN-151 / LAB-26, original LAB-31) and
result amendments (Doc 03 §5.5 RS-9, §5.6 RP-4, §6.6, KAN-152 / LAB-27,
original LAB-32) and critical notifications (Doc 03 §5.5 RS-10, §6.6, §8.5,
Doc 02 §5.6 v1.2, KAN-153 / LAB-28, original LAB-33).

POST /api/v1/samples/{id}/results — roles Technician, Pathologist (exact
§6.6 roles cell: "T P").
POST /api/v1/results/{id}/approve — roles Pathologist ONLY (exact §6.6
roles cell: "P").
POST /api/v1/results/{id}/withdraw — roles Technician, Pathologist, author
only (exact §6.6 roles cell: "T P (author only)").
POST /api/v1/results/{id}/amend — roles Technician, Pathologist (exact
§6.6 roles cell: "T P").
POST /api/v1/results/{id}/critical-notifications — roles Manager,
Pathologist (exact §6.6 roles cell: "M P").

Thin views: all business logic lives in ResultService.
"""

from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.branches.scope_views import IsInBranchScope
from apps.results.serializers import (
    CriticalNotificationSerializer,
    ResultAmendSerializer,
    ResultApproveSerializer,
    ResultEntrySerializer,
)
from apps.results.services import (
    RESULT_AMEND_ROLES,
    RESULT_APPROVE_ROLES,
    RESULT_ENTRY_ROLES,
    RESULT_NOTIFY_ROLES,
    RESULT_WITHDRAW_ROLES,
    ResultAlreadyEnteredError,
    ResultBatchValidationError,
    ResultError,
    ResultService,
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


class ResultEntryView(APIView):
    """POST /api/v1/samples/{id}/results — batch result entry (RS-V2).

    Branch scope (Doc 04 §8.5 Layer 3): no branch travels in the body (the
    sample carries it), so only the zero-assignment gate applies — BS-2.
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = None

    def post(self, request: Request, sample_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RESULT_ENTRY_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only Technician, Pathologist, or Owner may enter results.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ResultEntrySerializer(data=request.data)
        if not serializer.is_valid():
            first = next(iter(serializer.errors.values()))
            msg = first[0] if isinstance(first, list) else str(first)
            return Response(
                _format_error("validation_error", str(msg)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        try:
            payload = ResultService.enter_results(
                sample_id=sample_id,
                rows=data["results"],
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ResultBatchValidationError as exc:
            return Response(
                _format_error(exc.error_code, str(exc), {"rows": exc.rows}),
                status=exc.status_code,
            )
        except ResultAlreadyEnteredError as exc:
            return Response(
                _format_error(exc.error_code, str(exc), {"entered_by": exc.entered_by}),
                status=exc.status_code,
            )
        except ResultError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class ResultApproveView(APIView):
    """POST /api/v1/results/{id}/approve — clinical verification (RS-5/6/7/8/10)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, result_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RESULT_APPROVE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only a Pathologist or Owner may approve results.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ResultApproveSerializer(data=request.data)
        if not serializer.is_valid():
            first = next(iter(serializer.errors.values()))
            msg = first[0] if isinstance(first, list) else str(first)
            return Response(
                _format_error("validation_error", str(msg)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        try:
            payload = ResultService.approve_result(
                result_id=result_id,
                decision=data["decision"],
                note=data.get("note"),
                range_override=data.get("range_override", False),
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ResultError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_200_OK)


class ResultWithdrawView(APIView):
    """POST /api/v1/results/{id}/withdraw — author withdrawal (RS-4)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, result_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RESULT_WITHDRAW_ROLES:
            return Response(
                _format_error(
                    "withdraw_not_permitted",
                    "Only the author (Technician or Pathologist) may withdraw.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            payload = ResultService.withdraw_result(
                result_id=result_id,
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ResultError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_200_OK)


class ResultAmendView(APIView):
    """POST /api/v1/results/{id}/amend — amendment of an approved result (RS-9)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, result_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RESULT_AMEND_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only Technician or Pathologist may amend results.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ResultAmendSerializer(data=request.data)
        if not serializer.is_valid():
            first = next(iter(serializer.errors.values()))
            msg = first[0] if isinstance(first, list) else str(first)
            return Response(
                _format_error("validation_error", str(msg)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        try:
            payload = ResultService.amend_result(
                result_id=result_id,
                value=data.get("value"),
                unit=data.get("unit"),
                reason=data.get("reason"),
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ResultError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class CriticalNotificationView(APIView):
    """POST /api/v1/results/{id}/critical-notifications — critical-result
    notification record (§8.5, §6.6; roles cell exactly "M P")."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, result_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RESULT_NOTIFY_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only a Manager or Pathologist may record critical notifications.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CriticalNotificationSerializer(data=request.data)
        if not serializer.is_valid():
            first = next(iter(serializer.errors.values()))
            msg = first[0] if isinstance(first, list) else str(first)
            return Response(
                _format_error("validation_error", str(msg)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        try:
            payload = ResultService.record_critical_notification(
                result_id=result_id,
                notified_name=data["notified_name"],
                notified_at=data["notified_at"],
                read_back=data["read_back"],
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except ResultError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
                status=exc.status_code,
            )
        return Response(payload, status=status.HTTP_201_CREATED)
