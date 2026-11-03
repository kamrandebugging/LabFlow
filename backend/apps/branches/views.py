"""DRF views for Branch operations (Doc 04 §8.2, §8.3, §11.3, KAN-158 / LAB-33).

GET  /api/v1/branches            — roles Owner, Manager, Receptionist,
                                   Technician, Pathologist.
POST /api/v1/branches            — role Owner only.
PATCH /api/v1/branches/{id}      — role Owner only.
POST /api/v1/branches/{id}/close — role Owner only.
POST /api/v1/branches/{id}/reopen — role Owner only.

Thin views: all business logic lives in BranchService. The branch list is a
bare array (not cursor-paginated): branch counts are bounded by the plan
limit, and Doc 04 §15 names the response "list of branches" — an
endpoint-level exception to Doc 03 §6.1's cursor-pagination convention,
which that section itself permits ("unless an endpoint says otherwise").
"""

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.branches.serializers import (
    BranchCreateSerializer,
    BranchSerializer,
    BranchUpdateSerializer,
)
from apps.branches.services import (
    BRANCH_READ_ROLES,
    BRANCH_WRITE_ROLES,
    BranchError,
    BranchService,
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


def _branch_error_response(exc: BranchError) -> Response:
    return Response(
        _format_error(exc.error_code, str(exc) or exc.error_code, exc.details),
        status=exc.status_code,
    )


def _write_forbidden() -> Response:
    return Response(
        _format_error("forbidden", "Only the Lab Owner may manage branches."),
        status=status.HTTP_403_FORBIDDEN,
    )


class BranchListCreateView(APIView):
    """GET /api/v1/branches — list; POST /api/v1/branches — create."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BRANCH_READ_ROLES:
            return Response(
                _format_error("forbidden", "You may not list branches."),
                status=status.HTTP_403_FORBIDDEN,
            )
        include_closed = (
            request.query_params.get("include_closed", "").lower() == "true"
        )
        if include_closed and user.role not in BRANCH_WRITE_ROLES:
            # Doc 04 §15 marks include_closed "(O only)": explicit 403 rather
            # than silently ignoring the flag.
            return Response(
                _format_error(
                    "forbidden", "Only the Lab Owner may list closed branches."
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        branches = BranchService.list_branches(
            actor=user, include_closed=include_closed
        )
        return Response(BranchSerializer(branches, many=True).data)

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BRANCH_WRITE_ROLES:
            return _write_forbidden()
        serializer = BranchCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                _format_error(
                    "validation_error",
                    "Invalid branch data.",
                    serializer.errors,
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            branch = BranchService.create_branch(
                actor=user,
                data=serializer.validated_data,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except BranchError as exc:
            return _branch_error_response(exc)
        return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)


class BranchDetailView(APIView):
    """PATCH /api/v1/branches/{id} — update (If-Match supported, Doc 03 §6.1)."""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request: Request, branch_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BRANCH_WRITE_ROLES:
            return _write_forbidden()
        serializer = BranchUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                _format_error(
                    "validation_error",
                    "Invalid branch update data.",
                    serializer.errors,
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if_match = request.META.get("HTTP_IF_MATCH")
        try:
            branch = BranchService.update_branch(
                actor=user,
                branch_id=branch_id,
                data=serializer.validated_data,
                if_match=if_match,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except BranchError as exc:
            return _branch_error_response(exc)
        return Response(BranchSerializer(branch).data)


class BranchCloseView(APIView):
    """POST /api/v1/branches/{id}/close — soft-delete (Doc 04 §8.3)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, branch_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BRANCH_WRITE_ROLES:
            return _write_forbidden()
        try:
            branch = BranchService.close_branch(
                actor=user,
                branch_id=branch_id,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except BranchError as exc:
            return _branch_error_response(exc)
        return Response(BranchSerializer(branch).data)


class BranchReopenView(APIView):
    """POST /api/v1/branches/{id}/reopen — clear deleted_at (Doc 04 §8.3)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, branch_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in BRANCH_WRITE_ROLES:
            return _write_forbidden()
        try:
            branch = BranchService.reopen_branch(
                actor=user,
                branch_id=branch_id,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except BranchError as exc:
            return _branch_error_response(exc)
        return Response(BranchSerializer(branch).data)
