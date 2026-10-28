from __future__ import annotations

import factory

from apps.automation.models import WebhookDelivery
from tests.factories.base import TenantModelFactory


class WebhookDeliveryFactory(TenantModelFactory):
    class Meta:
        model = WebhookDelivery

    event = "report.ready"
    idempotency_key = factory.Sequence(lambda n: f"webhook-idem-{n}")
    payload_jsonb = factory.LazyAttribute(
        lambda o: {
            "event": o.event,
            "tenant_slug": "tenant-a",
            "callback_url": (
                "https://tenant-a.labflow.app/api/v1/webhooks/n8n/report-delivery"
            ),
            "idempotency_key": o.idempotency_key,
            "timestamp": "2026-10-20T08:15:30Z",
            "data": {"report_id": "00000000-0000-0000-0000-000000000001"},
        }
    )
    status = WebhookDelivery.Status.PENDING
    attempts = 0
    next_attempt_at = None
    last_error = None
