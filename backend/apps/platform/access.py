"""Subscription access mode computation with Redis caching (Doc 04 §11.2).

`tenant_access_mode(tenant)` returns "full" or "read_only":
- active → full
- past_due within 14 days of status change → full (grace, with banner)
- past_due after 14 days → read_only (automatic)
- cancelled | expired → read_only (at once)
- no subscription → read_only (safe default)

Result cached per tenant in Redis as `tenant:<slug>:access-mode`, 60s TTL.
Invalidated immediately by any platform write to that subscription.
"""

from datetime import timedelta
from typing import Final, Literal

from django.core.cache import cache
from django.utils import timezone

from apps.core.models import Subscription, Tenant

AccessMode = Literal["full", "read_only"]

ACCESS_MODE_CACHE_TTL: Final[int] = 60
GRACE_PERIOD_DAYS: Final[int] = 14


def access_mode_cache_key(slug: str) -> str:
    """Redis key for a tenant's cached access mode (Doc 04 §11.2)."""
    return f"tenant:{slug}:access-mode"


def invalidate_access_mode_cache(slug: str) -> None:
    """Drop the cached access mode so the next read recomputes it."""
    cache.delete(access_mode_cache_key(slug))


def tenant_access_mode(tenant: Tenant) -> AccessMode:
    """Compute full | read_only for a tenant from its subscription.

    Never raises: on any unexpected error returns "read_only" (safe default).
    """
    from contextlib import suppress

    cache_key = access_mode_cache_key(tenant.slug)
    with suppress(Exception):
        cached = cache.get(cache_key)
        if cached in ("full", "read_only"):
            return cached

    try:
        mode = _compute_access_mode(tenant)
    except Exception:
        mode = "read_only"

    with suppress(Exception):
        cache.set(cache_key, mode, ACCESS_MODE_CACHE_TTL)
    return mode


def _compute_access_mode(tenant: Tenant) -> AccessMode:
    """Read the latest subscription and derive the access mode."""
    sub = Subscription.objects.filter(tenant=tenant).order_by("-created_at").first()
    if sub is None:
        return "read_only"

    if sub.status == Subscription.Status.ACTIVE:
        return "full"

    if sub.status == Subscription.Status.PAST_DUE:
        grace_cutoff = timezone.now() - timedelta(days=GRACE_PERIOD_DAYS)
        # 14-day grace runs from when the status became past_due
        if sub.updated_at >= grace_cutoff:
            return "full"
        return "read_only"

    # cancelled | expired → read-only at once
    return "read_only"


def is_in_grace_period(tenant: Tenant) -> bool:
    """True when the tenant is past_due but still inside the 14-day grace.

    Used for the grace banner: full access with a payment banner to the Owner.
    """
    try:
        sub = (
            Subscription.objects.filter(
                tenant=tenant, status=Subscription.Status.PAST_DUE
            )
            .order_by("-created_at")
            .first()
        )
        if sub is None:
            return False
        grace_cutoff = timezone.now() - timedelta(days=GRACE_PERIOD_DAYS)
        return sub.updated_at >= grace_cutoff
    except Exception:
        return False
