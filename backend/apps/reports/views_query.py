"""DRF views for Reports list/detail and Exceptions list (Doc 03 §5.6, §6.1, §6.7).

Endpoints:
- GET /api/v1/reports — staff list with cursor pagination and filters.
- GET /api/v1/reports/<uuid:report_id> — staff detail with versions, deliveries, tokens.
- GET /api/v1/exceptions — actionable exceptions derived from real model states.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.reports.services_query import (
    REPORT_READ_ROLES,
    ReportExceptionsService,
    ReportQueryError,
    ReportQueryService,
)


def _problem_response(
    status_code: int,
    code: str,
    detail: str,
    title: str | None = None,
    errors: dict[str, Any] | None = None,
) -> Response:
    """Format RFC 9457 Problem+JSON error response (Doc 03 §6.1)."""
    if title is None:
        title = code.replace("_", " ").capitalize()
    problem_type = f"https://labflow.example/problems/{code.replace('_', '-')}"
    body: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "error": {"code": code, "message": detail},
    }
    if errors is not None:
        body["errors"] = errors
        body["error"]["details"] = errors
    return Response(body, status=status_code, content_type="application/problem+json")


def _check_staff_role(user: StaffUser) -> Response | None:
    if getattr(user, "role", None) not in REPORT_READ_ROLES:
        return _problem_response(
            status.HTTP_403_FORBIDDEN,
            "forbidden",
            "Only staff members are permitted to view clinical reports.",
        )
    return None


class ReportListView(APIView):
    """GET /api/v1/reports — cursor-paginated staff report list (Doc 03 §6.1, §6.7)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        denied = _check_staff_role(user)
        if denied is not None:
            return denied

        params = request.query_params
        limit = 50
        raw_limit = params.get("limit")
        if raw_limit is not None:
            try:
                limit = int(raw_limit)
                if limit < 1 or limit > 100:
                    raise ValueError("Limit must be between 1 and 100.")
            except (ValueError, TypeError):
                return _problem_response(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "validation_error",
                    "Invalid limit parameter: must be an integer between 1 and 100.",
                )

        try:
            results, next_cursor = ReportQueryService.list_reports(
                actor=user,
                status=params.get("status"),
                branch_id=params.get("branch") or params.get("branch_id"),
                patient=params.get("patient") or params.get("q"),
                created_after=params.get("created_after") or params.get("from"),
                created_before=params.get("created_before") or params.get("to"),
                cursor=params.get("cursor"),
                limit=limit,
            )
        except ReportQueryError as exc:
            return _problem_response(
                exc.status_code, exc.code, exc.message, errors=exc.details
            )

        return Response(
            {"results": results, "next_cursor": next_cursor},
            status=status.HTTP_200_OK,
        )


class ReportDetailView(APIView):
    """GET /api/v1/reports/<uuid:report_id> — staff detail (Doc 03 §6.7)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, report_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        denied = _check_staff_role(user)
        if denied is not None:
            return denied

        try:
            r_uuid = uuid.UUID(str(report_id))
        except (ValueError, TypeError, AttributeError):
            return _problem_response(
                status.HTTP_404_NOT_FOUND,
                "report_not_found",
                "Report not found.",
            )

        try:
            detail = ReportQueryService.get_report_detail(report_id=r_uuid, actor=user)
        except ReportQueryError as exc:
            return _problem_response(
                exc.status_code, exc.code, exc.message, errors=exc.details
            )

        return Response(detail, status=status.HTTP_200_OK)


class ExceptionsListView(APIView):
    """GET /api/v1/exceptions — triage queue derived from real data."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        denied = _check_staff_role(user)
        if denied is not None:
            return denied

        payload = ReportExceptionsService.get_exceptions(actor=user)
        return Response(payload, status=status.HTTP_200_OK)
