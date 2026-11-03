"""DRF views for Results — batch result entry (Doc 03 §5.5 RS-1/RS-2/RS-3/RS-V2,
§6.6, §8, KAN-150 / LAB-25, original LAB-30).

POST /api/v1/samples/{id}/results — roles Technician, Pathologist (exact
§6.6 roles cell: "T P").

Thin views: all business logic lives in ResultService.
"""

from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.results.serializers import ResultEntrySerializer
from apps.results.services import (
    RESULT_ENTRY_ROLES,
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
    """POST /api/v1/samples/{id}/results — batch result entry (RS-V2)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, sample_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RESULT_ENTRY_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only Technician or Pathologist may enter results.",
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
