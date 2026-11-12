"""Webhook retry sweep (Doc 06 §5.2, §12; Doc 10 §9; Doc 04 §13.2).

Beat runs this at minutes 3/18/33/48. The task fans out one sweep per
active tenant schema (never a schema loop): each child enters the tenant's
schema_context and retries due webhook_delivery rows.

A retry re-stamps timestamp at send time and re-signs; the stored
payload_jsonb keeps the original timestamp for audit and the idempotency
key never changes (§5.2 TS-2).
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

SWEEP_TASK_NAME = "webhooks.retry_pending_deliveries"


@shared_task(name=SWEEP_TASK_NAME)
def retry_pending_deliveries_task() -> dict[str, Any]:
    """Beat entrypoint: fan out the retry sweep across tenant schemas."""
    # Local imports: keep module importable without Django app registry.
    from apps.automation.models import WebhookDelivery
    from apps.automation.services import (
        _send_row,
        get_webhook_secret,
        webhook_url_for_event,
    )
    from apps.core.models import Tenant

    secret = get_webhook_secret()
    now = timezone.now()
    per_tenant: dict[str, int] = {}
    attempted_total = 0
    tenants = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
    for tenant in tenants:
        schema_name = tenant.schema_name
        attempted = 0
        try:
            with schema_context(schema_name):
                due = WebhookDelivery.objects.filter(
                    status__in=[
                        WebhookDelivery.Status.PENDING,
                        WebhookDelivery.Status.FAILED,
                    ],
                    next_attempt_at__lte=now,
                ).order_by("next_attempt_at")[:100]
                for row in due:
                    url = webhook_url_for_event(row.event)
                    if not url:
                        logger.warning(
                            "webhook_delivery %s has no URL for event %s; skipping",
                            row.idempotency_key,
                            row.event,
                        )
                        continue
                    _send_row(row, url, secret, restamp=True)
                    attempted += 1
        except Exception:
            logger.exception("webhook retry sweep failed for schema %s", schema_name)
            continue
        per_tenant[schema_name] = attempted
        attempted_total += attempted
    return {"attempted": attempted_total, "per_tenant": per_tenant}
