"""Share ledger read-only API endpoint (Doc 02 §5.8, Doc 05 §6; Screens 38–42).

GET /api/v1/referral-partners/ledger
Permissions: Owner + Manager
Cursor pagination: ?partner_id=, ?period= (YYYY-MM), ?rule_id=, ?limit=50, ?cursor=
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any, cast

from django.db.models import Count, Prefetch, Sum
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.partners.models import Settlement, SettlementLine, ShareLedgerEntry


def _format_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def _require_roles(user: StaffUser, roles: tuple[Role, ...]) -> Response | None:
    if user.role not in roles:
        return Response(
            _format_error("forbidden", "You may not access the share ledger."),
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


PERIOD_REGEX = re.compile(r"^\d{4}-\d{2}$")


class ShareLedgerListView(APIView):
    """GET /api/v1/referral-partners/ledger — Owner + Manager read-only view."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        denied = _require_roles(user, (Role.OWNER, Role.MANAGER))
        if denied is not None:
            return denied

        params = request.query_params

        # Filter: partner_id
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

        # Filter: period
        period = params.get("period")
        if period and not PERIOD_REGEX.match(period):
            return Response(
                _format_error("validation_error", "period must be YYYY-MM."),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Filter: rule_id
        rule_id = params.get("rule_id")
        rule_uuid: uuid.UUID | None = None
        if rule_id:
            try:
                rule_uuid = uuid.UUID(rule_id)
            except ValueError:
                return Response(
                    _format_error("validation_error", "rule_id must be a UUID."),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        # Limit
        try:
            limit_val = max(1, min(int(params.get("limit", 50)), 200))
        except (TypeError, ValueError):
            limit_val = 50

        # Base filtered queryset
        qs = ShareLedgerEntry.objects.all()
        if partner_uuid is not None:
            qs = qs.filter(referral_partner_id=partner_uuid)
        if period is not None:
            qs = qs.filter(period=period)
        if rule_uuid is not None:
            qs = qs.filter(rule_id=rule_uuid)

        # Totals computed from the filtered set (before pagination)
        totals_agg = qs.aggregate(count=Count("id"), amount=Sum("amount"))
        totals_count = totals_agg["count"] or 0
        totals_amount = totals_agg["amount"] or Decimal("0.00")

        # Ordering & cursor pagination
        qs = (
            qs.select_related("referral_partner", "rule")
            .prefetch_related(
                Prefetch(
                    "settlement_lines",
                    queryset=SettlementLine.objects.select_related(
                        "settlement"
                    ).exclude(settlement__status=Settlement.Status.CANCELLED),
                )
            )
            .order_by("-created_at", "-id")
        )

        cursor = params.get("cursor")
        if cursor:
            try:
                cursor_uuid = uuid.UUID(cursor)
                anchor = ShareLedgerEntry.objects.get(id=cursor_uuid)
                qs = qs.filter(created_at__lt=anchor.created_at) | qs.filter(
                    created_at=anchor.created_at, id__lt=anchor.id
                )
            except (ValueError, ShareLedgerEntry.DoesNotExist):
                return Response(
                    _format_error("validation_error", "Invalid cursor."),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        rows = list(qs[: limit_val + 1])
        next_cursor = str(rows[-1].id) if len(rows) > limit_val else None
        page_rows = rows[:limit_val]

        results = []
        for entry in page_rows:
            # Determine settlement from non-cancelled settlement lines
            settlement_obj = None
            for line in entry.settlement_lines.all():
                settlement_obj = {
                    "id": str(line.settlement.id),
                    "period": line.settlement.period,
                    "status": line.settlement.status,
                }
                break

            results.append(
                {
                    "id": str(entry.id),
                    "payment_id": str(entry.payment_id),
                    "referral_partner_id": str(entry.referral_partner_id),
                    "referral_partner_name": entry.referral_partner.name,
                    "rule_id": str(entry.rule_id) if entry.rule_id else None,
                    "rule_percent": f"{entry.rule.percent:.2f}" if entry.rule else None,
                    "amount": f"{entry.amount:.2f}",
                    "percent_applied": f"{entry.percent_applied:.2f}",
                    "basis_amount": f"{entry.basis_amount:.2f}",
                    "period": entry.period,
                    "created_at": entry.created_at.isoformat(),
                    "settlement": settlement_obj,
                }
            )

        return Response(
            {
                "results": results,
                "totals": {
                    "count": totals_count,
                    "amount": f"{totals_amount:.2f}",
                },
                "next_cursor": next_cursor,
            },
            status=status.HTTP_200_OK,
        )
