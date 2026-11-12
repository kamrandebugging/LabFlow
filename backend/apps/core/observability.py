"""Sentry wiring + a pure scrubber (LAB-49 Phase 3.7, SE-30–SE-33, API8 A8-9).

The scrubber is pure and unit-testable: it removes credentials, tokens and
patient identifiers from an event before it leaves the process. ``init_sentry``
is a no-op when ``SENTRY_DSN`` is empty or the SDK is not installed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "token",
        "access",
        "refresh",
        "refresh_token",
        "authorization",
        "cookie",
        "set-cookie",
        "secret",
        "api_key",
        "callback_key",
        "totp",
        "code",
        "otp",
        "signature",
        "sig",
        "email",
        "phone",
        "date_of_birth",
        "dob",
        "mrn",
        "notified_name",
        "patient_name",
    }
)
_REDACTED = "[Filtered]"
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_HEX_RE = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)


def _scrub_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                _REDACTED
                if str(key).lower() in _SENSITIVE_KEYS
                else _scrub_mapping(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_mapping(item) for item in value]
    if isinstance(value, str):
        value = _EMAIL_RE.sub(_REDACTED, value)
        return _LONG_HEX_RE.sub(_REDACTED, value)
    return value


def scrub_event(event: dict[str, Any], _hint: Any = None) -> dict[str, Any]:
    """Remove secrets/PII from a Sentry event (pure function)."""
    scrubbed = _scrub_mapping(event)
    headers = scrubbed.get("request", {}).get("headers")
    if isinstance(headers, dict):
        for key in list(headers):
            if key.lower() in _SENSITIVE_KEYS:
                headers[key] = _REDACTED
    return scrubbed


def init_sentry() -> None:
    """Initialise Sentry with the scrubber when a DSN is configured."""
    from django.conf import settings

    dsn = getattr(settings, "SENTRY_DSN", "") or ""
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.warning("Sentry SDK unavailable: %s", exc)
        return

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration()],
        environment=getattr(settings, "SENTRY_ENVIRONMENT", "production"),
        send_default_pii=False,
        traces_sample_rate=0.0,
        before_send=scrub_event,
    )
