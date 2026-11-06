"""Platform overview metrics — public-schema reads only (Doc 04 §12.2, TP-4).

Every figure is derived from public-schema rows plus PostgreSQL catalogues.
This module must never touch a tenant schema: the master dashboard reports on
the platform's own book of business, not on tenant content.
"""

from contextlib import suppress
from decimal import Decimal
from typing import Any, Final

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Subscription, Tenant
from apps.platform.access import is_in_grace_period, tenant_access_mode
from apps.platform.views import (
    IsAuthenticatedPlatformUser,
    PlatformJWTAuthentication,
)

METRICS_CACHE_KEY: Final[str] = "platform:metrics:overview"
METRICS_CACHE_TTL_SECONDS: Final[int] = 60


def _money(value: Decimal | None) -> str:
    """Money is always a 2-decimal string in PKR (never a JSON number)."""
    amount = value if value is not None else Decimal("0.00")
    return f"{amount.quantize(Decimal('0.01'))}"


def compute_overview() -> dict[str, Any]:
    """Build the overview payload from public-schema data.

    ``founding_slots_total`` comes from configuration and
    ``founding_slots_used`` counts active subscriptions on the plan named by
    ``PLATFORM_FOUNDING_PLAN_NAME``; nothing here is hard-coded or invented.
    """
    tenants = list(Tenant.objects.exclude(schema_name="public"))
    status_counts: dict[str, int] = {}
    for tenant in tenants:
        status_counts[tenant.status] = status_counts.get(tenant.status, 0) + 1

    mrr = Subscription.objects.filter(status=Subscription.Status.ACTIVE).aggregate(
        total=Sum("plan__price")
    )["total"]

    founding_plan_name = str(
        getattr(settings, "PLATFORM_FOUNDING_PLAN_NAME", "Founding")
    )
    founding_used = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        plan__name__iexact=founding_plan_name,
    ).count()

    census = {"full": 0, "read_only": 0, "grace": 0}
    for tenant in tenants:
        if tenant.status in (Tenant.Status.DELETED, Tenant.Status.PROVISIONING):
            continue
        if is_in_grace_period(tenant):
            census["grace"] += 1
        elif tenant_access_mode(tenant) == "full":
            census["full"] += 1
        else:
            census["read_only"] += 1

    return {
        "total_labs": len(tenants),
        "active_labs": status_counts.get(Tenant.Status.ACTIVE, 0),
        "suspended_labs": status_counts.get(Tenant.Status.SUSPENDED, 0),
        "provisioning_labs": status_counts.get(Tenant.Status.PROVISIONING, 0),
        "mrr_pkr": _money(mrr if isinstance(mrr, Decimal) else None),
        "overdue_count": Subscription.objects.filter(
            status=Subscription.Status.PAST_DUE
        ).count(),
        "lifetime_sold": Subscription.objects.count(),
        "founding_slots_used": founding_used,
        "founding_slots_total": int(
            getattr(settings, "PLATFORM_FOUNDING_SLOTS_TOTAL", 0) or 0
        ),
        "access_mode_census": census,
        "generated_at": timezone.now().isoformat(),
    }


class PlatformOverviewMetricsView(APIView):
    """GET /api/v1/platform/metrics/overview (60 s Redis cache)."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            cached = cache.get(METRICS_CACHE_KEY)
            if isinstance(cached, dict):
                return Response(cached, status=200)
        except Exception:
            cached = None

        payload = compute_overview()

        # A metrics cache write failure is not worth failing the dashboard over.
        with suppress(Exception):
            cache.set(METRICS_CACHE_KEY, payload, timeout=METRICS_CACHE_TTL_SECONDS)

        return Response(payload, status=200)
