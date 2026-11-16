"""Per-day sample statistics for the Owner dashboard waffle.

GET /api/v1/samples/daily?days=7|14|30

Returns one entry per calendar day in the window (tenant timezone), oldest
first, with the real per-status counts. Days with no samples are returned with
zeroes so the client can render Capacity slots instead of inventing volume.

No median turnaround is returned: the API has no per-sample ready timestamp on
the sample row, and deriving it from events would need an index this batch does
not add. The field is present and null so the contract is stable.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.branches.scope_views import IsInBranchScope
from apps.branches.scoping import effective_branch_ids
from apps.samples.models import Sample
from apps.samples.views import SAMPLE_READ_ROLES

TENANT_TZ = ZoneInfo("Asia/Karachi")
ALLOWED_RANGES = (7, 14, 30)


class SampleDailyStatsView(APIView):
    """GET /api/v1/samples/daily - per-day samples grouped by status."""

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        role = getattr(user, "role", None)
        if (
            role is not None
            and role not in SAMPLE_READ_ROLES
            and str(role).lower() not in SAMPLE_READ_ROLES
        ):
            return Response(
                {
                    "error": {
                        "code": "forbidden",
                        "message": "Role not permitted to view samples.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        raw_days = request.query_params.get("days", "7")
        try:
            days = int(str(raw_days))
        except (TypeError, ValueError):
            days = -1
        if days not in ALLOWED_RANGES:
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "days must be one of 7, 14 or 30.",
                    }
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        today = timezone.localdate(timezone=TENANT_TZ)
        start = today - timedelta(days=days - 1)

        queryset = Sample.objects.filter(
            collected_at__date__gte=start,
            collected_at__date__lte=today,
        )

        if not getattr(user, "is_tenant_wide", False):
            branch_ids = effective_branch_ids(user)
            if not branch_ids:
                return Response(
                    {
                        "from": start.isoformat(),
                        "to": today.isoformat(),
                        "days": [],
                    },
                    status=status.HTTP_200_OK,
                )
            queryset = queryset.filter(branch_id__in=branch_ids)

        rows = (
            queryset.annotate(day=TruncDate("collected_at", tzinfo=TENANT_TZ))
            .values("day", "status")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        by_day: dict[str, dict[str, int]] = {}
        for row in rows:
            day = row["day"]
            key = day.isoformat() if hasattr(day, "isoformat") else str(day)
            bucket = by_day.setdefault(key, {})
            bucket[str(row["status"])] = int(row["count"])

        payload: list[dict[str, Any]] = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            key = day.isoformat()
            statuses = by_day.get(key, {})
            total = sum(statuses.values())
            payload.append(
                {
                    "date": key,
                    "total": total,
                    "statuses": {
                        "collected": statuses.get("collected", 0),
                        "received": statuses.get("received", 0),
                        "in_process": statuses.get("in_process", 0),
                        "ready": statuses.get("ready", 0),
                        "rejected": statuses.get("rejected", 0),
                        "cancelled": statuses.get("cancelled", 0),
                    },
                    "median_turnaround_seconds": None,
                }
            )

        return Response(
            {
                "from": start.isoformat(),
                "to": today.isoformat(),
                "days": payload,
            },
            status=status.HTTP_200_OK,
        )
