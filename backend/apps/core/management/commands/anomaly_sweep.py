"""Daily business-flow anomaly sweep (LAB-49 Phase 2.9, API6 A6-8).

Flags, per tenant, the patterns OWASP API6 describes as machine-speed abuse:

- refund value today above 2x the 30-day daily mean,
- any discount above 50% of the subtotal today,
- invoice creation today above 3x the 30-day daily mean.

v1 alerts only: each hit writes one append-only ``PlatformAudit`` row
(``security.anomaly``) and is logged. Nothing is blocked here — the money
velocity caps already bound the blast radius.

Usage: ``python manage.py anomaly_sweep`` (Celery beat runs it daily).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Flag refund/discount/invoice-creation anomalies per tenant."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--threshold", type=float, default=3.0)

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.core.models import Tenant

        days = max(1, int(options["days"]))
        threshold = float(options["threshold"])
        flagged = 0
        tenants = Tenant.objects.exclude(schema_name="public").order_by("schema_name")
        for tenant in tenants:
            with schema_context(tenant.schema_name):
                flagged += self._sweep_tenant(tenant, days, threshold)
        self.stdout.write(
            self.style.SUCCESS(f"Anomaly sweep complete: {flagged} flag(s).")
        )

    def _sweep_tenant(self, tenant: Any, days: int, threshold: float) -> int:
        from apps.billing.models import Invoice, Payment

        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = today - timedelta(days=days)
        flags = 0

        refund_today = Payment.objects.filter(
            kind=Payment.Kind.REFUND, created_at__gte=today
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        refund_window = Payment.objects.filter(
            kind=Payment.Kind.REFUND,
            created_at__gte=window_start,
            created_at__lt=today,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        refund_mean = Decimal(refund_window) / Decimal(days)
        if refund_today > 0 and refund_today > refund_mean * Decimal("2"):
            flags += self._audit(
                tenant,
                "refund_spike",
                {
                    "today": str(refund_today),
                    "daily_mean": str(refund_mean.quantize(Decimal("0.01"))),
                },
            )

        big_discounts = Invoice.objects.filter(
            created_at__gte=today,
            discount_amount__gt=0,
        )
        for invoice in big_discounts.iterator():
            subtotal = invoice.subtotal or Decimal("0.00")
            if subtotal > 0 and invoice.discount_amount / subtotal >= Decimal("0.5"):
                flags += self._audit(
                    tenant,
                    "large_discount",
                    {
                        "invoice_id": str(invoice.id),
                        "subtotal": str(subtotal),
                        "discount": str(invoice.discount_amount),
                    },
                )

        invoices_today = Invoice.objects.filter(created_at__gte=today).count()
        invoices_window = Invoice.objects.filter(
            created_at__gte=window_start, created_at__lt=today
        ).count()
        invoice_mean = invoices_window / days
        if invoices_today > max(threshold, threshold * invoice_mean):
            flags += self._audit(
                tenant,
                "invoice_creation_spike",
                {"today": invoices_today, "daily_mean": round(invoice_mean, 2)},
            )

        if flags:
            logger.warning(
                "security_anomaly tenant=%s flags=%d", tenant.schema_name, flags
            )
        return flags

    def _audit(self, tenant: Any, kind: str, detail: dict[str, Any]) -> int:
        from apps.core.models import PlatformAudit

        PlatformAudit.objects.create(
            actor_id=None,
            action="security.anomaly",
            entity_type="tenant",
            entity_id=tenant.id,
            before_jsonb=None,
            after_jsonb={"anomaly": kind, "tenant": tenant.schema_name, **detail},
            ip=None,
            user_agent="anomaly_sweep",
        )
        return 1
