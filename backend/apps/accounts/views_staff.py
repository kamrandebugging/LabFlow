"""Staff branch assignments and Owner-only Staff CRUD.

GET /api/v1/staff/{id}/branches — roles O; a Manager may read the roster of
their own branches (SB-5).
PUT /api/v1/staff/{id}/branches — roles O ONLY (SB-5); the body REPLACES the
whole assignment set atomically (SB-4, SB-6).

Staff CRUD (D4, FR-2, S2/S3/S4/S14):
GET/POST /api/v1/staff
GET/PATCH /api/v1/staff/{id}
POST /api/v1/staff/{id}/deactivate
POST /api/v1/staff/{id}/reactivate
POST /api/v1/staff/{id}/reset-password

Thin views: role checks, strict serialization, error mapping. All business
logic lives in StaffBranchService / StaffService.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.accounts.services import StaffBranchError, StaffBranchService
from apps.accounts.staff_service import StaffError, StaffService


class StaffWriteThrottle(SimpleRateThrottle):
    """S8: rate-limit high-value staff mutations per acting session/user."""

    scope = "staff_write"

    def get_rate(self) -> str:
        return "60/hour"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        return f"staff_write:{user.id}"


class StaffWriteThrottleMixin:
    """Throttle only unsafe staff methods; list/detail reads stay unlimited."""

    def get_throttles(self) -> list[Any]:
        request = getattr(self, "request", None)
        if getattr(request, "method", "") in ("POST", "PUT", "PATCH", "DELETE"):
            return [StaffWriteThrottle()]
        return []


def _get_client_ip(request: Request) -> str:
    """Return a validated IP, never an attacker-chosen XFF string."""
    import ipaddress

    candidates = [
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip(),
        request.META.get("REMOTE_ADDR", ""),
    ]
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return ""


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


def _staff_error(exc: StaffError) -> Response:
    body: dict[str, Any] = {
        "error": {
            "code": exc.error_code,
            "message": str(exc) or exc.error_code,
        }
    }
    if exc.details is not None:
        body["error"]["details"] = exc.details
    return Response(body, status=exc.status_code)


def _user_agent(request: Request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")


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
                user_agent=_user_agent(request),
            )
        except StaffBranchError as exc:
            return _error(exc)
        return Response(rows, status=status.HTTP_200_OK)


class StaffCollectionView(StaffWriteThrottleMixin, APIView):
    """GET /api/v1/staff — paginated list; POST /api/v1/staff — create."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        actor = cast(StaffUser, request.user)
        try:
            payload = StaffService.list_staff(
                actor,
                limit=int(request.query_params.get("limit", 50) or 50),
                cursor=request.query_params.get("cursor"),
                status_filter=request.query_params.get("status"),
                role_filter=request.query_params.get("role"),
                q=request.query_params.get("q"),
            )
        except (TypeError, ValueError):
            return _staff_error(
                StaffError("limit must be an integer.", details={"limit": "invalid"})
            )
        except StaffError as exc:
            return _staff_error(exc)
        return Response(payload, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        actor = cast(StaffUser, request.user)
        try:
            payload = StaffService.create_staff(
                actor,
                request.data,
                ip=_get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except StaffError as exc:
            return _staff_error(exc)
        return Response(payload, status=status.HTTP_201_CREATED)


class StaffDetailView(StaffWriteThrottleMixin, APIView):
    """GET / PATCH /api/v1/staff/{id}."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, staff_id: uuid.UUID) -> Response:
        actor = cast(StaffUser, request.user)
        try:
            payload = StaffService.get_staff(actor, staff_id)
        except StaffError as exc:
            return _staff_error(exc)
        return Response(payload, status=status.HTTP_200_OK)

    def patch(self, request: Request, staff_id: uuid.UUID) -> Response:
        actor = cast(StaffUser, request.user)
        try:
            payload = StaffService.update_staff(
                actor,
                staff_id,
                request.data,
                ip=_get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except StaffError as exc:
            return _staff_error(exc)
        return Response(payload, status=status.HTTP_200_OK)


class StaffDeactivateView(StaffWriteThrottleMixin, APIView):
    """POST /api/v1/staff/{id}/deactivate — deactivate-only, never delete."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, staff_id: uuid.UUID) -> Response:
        actor = cast(StaffUser, request.user)
        try:
            payload = StaffService.deactivate_staff(
                actor,
                staff_id,
                ip=_get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except StaffError as exc:
            return _staff_error(exc)
        return Response(payload, status=status.HTTP_200_OK)


class StaffReactivateView(StaffWriteThrottleMixin, APIView):
    """POST /api/v1/staff/{id}/reactivate."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, staff_id: uuid.UUID) -> Response:
        actor = cast(StaffUser, request.user)
        try:
            payload = StaffService.reactivate_staff(
                actor,
                staff_id,
                ip=_get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except StaffError as exc:
            return _staff_error(exc)
        return Response(payload, status=status.HTTP_200_OK)


class StaffResetPasswordView(StaffWriteThrottleMixin, APIView):
    """POST /api/v1/staff/{id}/reset-password — temp password shown once."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, staff_id: uuid.UUID) -> Response:
        actor = cast(StaffUser, request.user)
        try:
            payload = StaffService.reset_password(
                actor,
                staff_id,
                ip=_get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except StaffError as exc:
            return _staff_error(exc)
        return Response(payload, status=status.HTTP_200_OK)
