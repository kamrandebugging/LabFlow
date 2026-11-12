"""Fresh-TOTP step-up for money movement (LAB-49 Phase 2.8, API6 A6-7).

A settlement approval / mark-paid / send, or a refund above the Manager
ceiling, requires either a freshly verified TOTP code (``X-StepUp-Token``) or a
step-up marker written when that code was verified within the last five
minutes. The marker is per user and shared across workers (Redis cache).

The control is a tripwire on top of the role gate: it does not replace it.
When ``STEP_UP_ENABLED`` is false (tests/local), it is a no-op; production
settings turn it on.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import RoleDenied

logger = logging.getLogger(__name__)

STEP_UP_WINDOW_SECONDS = 300


def _marker_key(user_id: Any) -> str:
    return f"auth:stepup:{user_id}"


def has_fresh_step_up(user_id: Any) -> bool:
    try:
        return cache.get(_marker_key(user_id)) is not None
    except Exception:
        return False


def _verify_totp(user: Any, code: str) -> bool:
    from apps.accounts.auth_service import AuthService

    secret = getattr(user, "totp_secret_encrypted", None)
    if not secret:
        return False
    try:
        import pyotp

        raw = AuthService._get_fernet().decrypt(secret.encode()).decode()
        return bool(pyotp.TOTP(raw).verify(code, valid_window=1))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Step-up TOTP verification failed: %s", exc)
        return False


def enforce_step_up(user: Any, request: Any, *, action: str) -> None:
    """Require fresh TOTP proof for a sensitive money action.

    Skipped entirely when disabled, or for accounts with no TOTP (they cannot
    produce a code; their role gate still applies and the Owner must enrol).
    """
    if not getattr(settings, "STEP_UP_ENABLED", False):
        return
    if not getattr(user, "totp_enabled", False):
        return
    user_id = getattr(user, "id", None)
    if user_id and has_fresh_step_up(user_id):
        return

    code = ""
    headers = getattr(request, "headers", None)
    if headers is not None:
        code = headers.get("X-StepUp-Token", "") or ""
    if not code:
        raise RoleDenied(f"Fresh TOTP required before {action}.")
    if not _verify_totp(user, code.strip()):
        raise RoleDenied(f"Fresh TOTP required before {action}.")
    if user_id:
        cache.set(_marker_key(user_id), "1", timeout=STEP_UP_WINDOW_SECONDS)


def clear_step_up(user_id: Any) -> None:
    """Drop the marker (called after a sensitive action completes)."""
    try:
        cache.delete(_marker_key(user_id))
    except Exception:
        logger.warning("Failed to clear step-up marker for %s", user_id)
