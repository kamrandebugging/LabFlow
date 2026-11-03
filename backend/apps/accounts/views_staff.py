"""Staff branch assignment views (Doc 04 §8.4, §15, KAN-159 / LAB-34).

GET /api/v1/staff/{id}/branches — roles O; a Manager may read the roster of
their own branches (SB-5).
PUT /api/v1/staff/{id}/branches — roles O ONLY (SB-5); the body REPLACES the
whole assignment set atomically (SB-4, SB-6).

Thin views: role checks, strict serialization, error mapping. All business
logic lives in StaffBranchService (apps/accounts/services.py).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.accounts.services import StaffBranchError, StaffBranchService


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _error(exc: StaffBranchError) -> Response:
    body: dict[str, Any] = {
        "error": {
            "code": exc.error_code,
            "message": str(exc) or exc.error_code,
        }
    }
    if exc.details is not None:
        body["error"]["details"] = exc.details
    return Response(body, status=exc.status_code)


class StaffBranchesView(APIView):
    """GET + PUT /api/v1/staff/{id}/branches."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, staff_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        try:
            rows = StaffBranchService.list_assignments(actor=user, staff_id=staff_id)
        except StaffBranchError as exc:
            return _error(exc)
        return Response(rows, status=status.HTTP_200_OK)

    def put(self, request: Request, staff_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        try:
            rows = StaffBranchService.replace_assignments(
                actor=user,
                staff_id=staff_id,
                items=request.data,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except StaffBranchError as exc:
            return _error(exc)
        return Response(rows, status=status.HTTP_200_OK)
