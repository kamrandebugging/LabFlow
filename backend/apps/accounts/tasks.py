"""Celery tasks for accounts app (KAN-106)."""

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import PasswordResetToken
from apps.core.models import Tenant

logger = logging.getLogger(__name__)


@shared_task(name="accounts.cleanup_expired_tokens")
def cleanup_expired_tokens_task() -> dict[str, Any]:
    """Purge password_reset_token rows created > 30 days ago across tenants

    (Doc 02 §5.11, Doc 04 §13.2).
    """
    now = timezone.now()
    cutoff = now - timedelta(days=30)
    total_purged = 0
    tenant_results: dict[str, int] = {}

    # Iterate over all tenant schemas (Doc 04 §13.2 TP-5 fan-out pattern)
    tenants = Tenant.objects.exclude(schema_name="public")
    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                deleted_count, _ = PasswordResetToken.objects.filter(
                    created_at__lt=cutoff
                ).delete()
                tenant_results[tenant.schema_name] = deleted_count
                total_purged += deleted_count
                logger.info(
                    "accounts.cleanup_expired_tokens: tenant_slug=%s schema=%s "
                    "purged=%d tokens older than %s",
                    tenant.slug,
                    tenant.schema_name,
                    deleted_count,
                    cutoff.isoformat(),
                )
        except Exception:
            logger.exception(
                "accounts.cleanup_expired_tokens: failed for tenant_slug=%s schema=%s",
                tenant.slug,
                tenant.schema_name,
            )

    return {
        "status": "success",
        "total_purged": total_purged,
        "tenants": tenant_results,
    }
