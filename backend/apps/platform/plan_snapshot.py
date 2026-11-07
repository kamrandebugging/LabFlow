"""Single source of truth for a tenant's commercial plan snapshot.

The Labs List (``/api/v1/platform/tenants``) and the Lab Detail screen
(``/api/v1/platform/tenants/<id>``) must always agree on plan name and price.
Both therefore read the same row: the tenant's ACTIVE subscription joined to
its plan, falling back to the most recent subscription when none is active.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from apps.core.models import Subscription


def _pick(subscriptions: list[Subscription]) -> Subscription | None:
    """Prefer the newest ACTIVE subscription, else the newest of any status."""
    active = [s for s in subscriptions if s.status == Subscription.Status.ACTIVE]
    if active:
        return active[0]
    return subscriptions[0] if subscriptions else None


def tenant_plan_snapshot(
    tenant_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict[str, Any] | None]:
    """Return ``{tenant_id: {name, price, status, plan_id, is_active}}``.

    ``price`` is a 2dp PKR string from the Plan row — never a client fallback.
    A demo lab with no paid subscription is reported with the real plan price
    of its (trial) subscription plus ``is_demo``/``status`` so the UI can label
    it instead of printing PKR 0.00.
    """
    if not tenant_ids:
        return {}

    grouped: dict[uuid.UUID, list[Subscription]] = {tid: [] for tid in tenant_ids}
    for sub in (
        Subscription.objects.filter(tenant_id__in=tenant_ids)
        .select_related("plan")
        .order_by("-created_at")
    ):
        grouped.setdefault(sub.tenant_id, []).append(sub)

    snapshots: dict[uuid.UUID, dict[str, Any] | None] = {}
    for tenant_id, subs in grouped.items():
        sub = _pick(subs)
        if sub is None or sub.plan is None:
            snapshots[tenant_id] = None
            continue
        plan = sub.plan
        snapshots[tenant_id] = {
            "plan_id": str(plan.id),
            "name": plan.name,
            "price": str(Decimal(plan.price).quantize(Decimal("0.01"))),
            "status": sub.status,
            "is_active_plan": plan.is_active,
            "is_demo": sub.status != Subscription.Status.ACTIVE,
        }
    return snapshots
