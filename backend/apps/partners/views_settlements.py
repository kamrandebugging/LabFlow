"""Settlement workflow endpoints (Doc 05 §7, §10; KAN-261 / LAB-42).

GET    /api/v1/settlements                 O, M — list (filters: partner_id,
                                           period, status)
GET    /api/v1/settlements/{id}            O, M — detail with lines
POST   /api/v1/settlements/{id}/approve    O — approve a DRAFT (If-Match)
POST   /api/v1/settlements/{id}/cancel     O — cancel a DRAFT (If-Match)
POST   /api/v1/settlements/{id}/mark-paid  O — confirm payment (If-Match)
POST   /api/v1/settlements/{id}/send       O — (re-)send the statement

Error shape: {"error": {"code", "message", "details?}} (Doc 03 §6.1).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.partners.services_settlements import (
    InvalidStateTransitionError,
    SettlementError,
    SettlementNotCancellableError,
    SettlementService,
    settlement_etag,
)


def _format_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def _get_client_ip(request: Request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _service_error_response(exc: SettlementError) -> Response:
    details: dict[str, Any] | None = None
    if getattr(exc, "error_code", "") == "version_conflict":
        details = getattr(exc, "current_state", None)
    return Response(
        _format_error(exc.error_code, str(exc) or exc.error_code, details),
        status=exc.status_code,
    )


def _require_roles(user: StaffUser, roles: tuple[Role, ...]) -> Response | None:
    if user.role not in roles:
        return Response(
            _format_error("forbidden", "You may not access settlements."),
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


class SettlementListView(APIView):
    """GET /api/v1/settlements — O, M (Doc 05 §10.2)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        denied = _require_roles(user, (Role.OWNER, Role.MANAGER))
        if denied is not None:
            return denied
        params = request.query_params
        partner_id = params.get("partner_id")
        partner_uuid: uuid.UUID | None = None
        if partner_id:
            try:
                partner_uuid = uuid.UUID(partner_id)
            except ValueError:
                return Response(
                    _format_error("validation_error", "partner_id must be a UUID."),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        try:
            limit = int(params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        try:
            rows, next_cursor = SettlementService.list_settlements(
                partner_id=partner_uuid,
                period=params.get("period"),
                status=params.get("status"),
                limit=limit,
                cursor=params.get("cursor"),
            )
        except SettlementError as exc:
            return _service_error_response(exc)
        return Response(
            {
                "results": [SettlementService.to_dict(row) for row in rows],
                "next_cursor": next_cursor,
            },
            status=status.HTTP_200_OK,
        )


class SettlementDetailView(APIView):
    """GET /api/v1/settlements/{id} — O, M, detail with lines."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _require_roles(user, (Role.OWNER, Role.MANAGER))
        if denied is not None:
            return denied
        try:
            settlement = SettlementService.get_settlement(id)
        except SettlementError as exc:
            return _service_error_response(exc)
        return Response(
            SettlementService.to_dict(settlement, include_lines=True),
            status=status.HTTP_200_OK,
        )


def _mutate_view(
    request: Request,
    id: uuid.UUID,
    action: str,
) -> Response:
    """Shared handler for approve / cancel / mark-paid (AP-2: If-Match)."""
    user = cast(StaffUser, request.user)
    if user.role != Role.OWNER:
        return Response(
            _format_error("forbidden", "Only the Owner may do this."),
            status=status.HTTP_403_FORBIDDEN,
        )
    tenant = getattr(request, "tenant", None)
    if_match = request.META.get("HTTP_IF_MATCH")
    ip = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    try:
        if action == "approve":
            settlement = SettlementService.approve(
                actor=user,
                tenant=tenant,
                settlement_id=id,
                if_match=if_match,
                ip=ip,
                user_agent=user_agent,
            )
        elif action == "cancel":
            settlement = SettlementService.cancel(
                actor=user,
                tenant=tenant,
                settlement_id=id,
                if_match=if_match,
                ip=ip,
                user_agent=user_agent,
            )
        else:  # mark-paid
            reference = (
                request.data.get("reference")
                if isinstance(request.data, dict)
                else None
            )
            settlement = SettlementService.mark_paid(
                actor=user,
                tenant=tenant,
                settlement_id=id,
                if_match=if_match,
                reference=reference,
                ip=ip,
                user_agent=user_agent,
            )
    except SettlementError as exc:
        # §12.2: a stale token returns the settlement's current state.
        if getattr(exc, "error_code", "") == "version_conflict":
            try:
                current = SettlementService.get_settlement(id)
                exc.current_state = {  # type: ignore[attr-defined]
                    "id": str(current.id),
                    "status": current.status,
                    "version": settlement_etag(current),
                }
            except SettlementError:
                pass
        return _service_error_response(exc)
    return Response(
        SettlementService.to_dict(settlement, include_lines=True),
        status=status.HTTP_200_OK,
    )


class SettlementApproveView(APIView):
    """POST /api/v1/settlements/{id}/approve — O (ST-9, ST-10)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, id: uuid.UUID) -> Response:
        return _mutate_view(request, id, "approve")


class SettlementCancelView(APIView):
    """POST /api/v1/settlements/{id}/cancel — O (ST-16..ST-19)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, id: uuid.UUID) -> Response:
        return _mutate_view(request, id, "cancel")


class SettlementMarkPaidView(APIView):
    """POST /api/v1/settlements/{id}/mark-paid — O (ST-13..ST-15)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, id: uuid.UUID) -> Response:
        return _mutate_view(request, id, "mark-paid")


class SettlementSendView(APIView):
    """POST /api/v1/settlements/{id}/send — O (DL-6)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role != Role.OWNER:
            return Response(
                _format_error("forbidden", "Only the Owner may do this."),
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant = getattr(request, "tenant", None)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        try:
            notification = SettlementService.send(
                actor=user,
                tenant=tenant,
                settlement_id=id,
                ip=ip,
                user_agent=user_agent,
            )
        except SettlementError as exc:
            # A state error on send also carries the current settlement.
            if isinstance(exc, InvalidStateTransitionError):
                try:
                    current = SettlementService.get_settlement(id)
                    exc.current_state = {  # type: ignore[attr-defined]
                        "id": str(current.id),
                        "status": current.status,
                        "version": settlement_etag(current),
                    }
                except SettlementError:
                    pass
                details = getattr(exc, "current_state", None)
                return Response(
                    _format_error(exc.error_code, str(exc), details),
                    status=exc.status_code,
                )
            return _service_error_response(exc)
        return Response(
            {
                "notification_id": str(notification.id),
                "status": notification.status,
                "channel": notification.channel,
            },
            status=status.HTTP_200_OK,
        )


# Re-export for the version_conflict detail branch above.
_ = SettlementNotCancellableError
