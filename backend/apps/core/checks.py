"""Django system checks for outbound-webhook configuration (LAB-49 Phase 4.1).

A typo'd or malicious ``N8N_WEBHOOK_URL`` should fail startup, not the first
delivery. The check is skipped in DEBUG so local development without n8n keeps
working.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Error, register


@register()
def check_outbound_webhooks(app_configs: Any, **kwargs: Any) -> list[Error]:
    if getattr(settings, "DEBUG", False):
        return []
    from apps.core.safe_fetch import UnsafeURLError, validate_configured_webhooks

    try:
        validate_configured_webhooks(resolve=False)
    except UnsafeURLError as exc:
        return [
            Error(
                f"Outbound webhook configuration is unsafe: {exc}",
                id="core.E001",
            )
        ]
    return []
