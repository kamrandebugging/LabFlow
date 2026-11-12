"""Accounts Celery tasks (LAB-49 fix-up: keep network I/O off the request path)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="accounts.cleanup_expired_tokens")
def cleanup_expired_tokens_task() -> dict[str, Any]:
    """Purge password-reset tokens older than 30 days across tenant schemas."""
    from django.utils import timezone
    from django_tenants.utils import schema_context

    from apps.accounts.models import PasswordResetToken
    from apps.core.models import Tenant

    cutoff = timezone.now() - timedelta(days=30)
    total = 0
    for tenant in Tenant.objects.exclude(schema_name="public"):
        with schema_context(tenant.schema_name):
            deleted, _ = PasswordResetToken.objects.filter(
                created_at__lt=cutoff
            ).delete()
            logger.info(
                "accounts.cleanup_expired_tokens purged %s rows for %s",
                deleted,
                tenant.schema_name,
            )
            total += deleted
    return {"status": "success", "deleted": total}


@shared_task(name="accounts.send_password_reset_email", max_retries=3)
def send_password_reset_email_task(
    email: str, display_name: str, link: str
) -> dict[str, Any]:
    """Deliver one password-reset link; retry transient SMTP failures."""
    from apps.accounts.emails import send_password_reset_email_to

    sent = send_password_reset_email_to(email, display_name, link)
    return {"sent": sent}
