"""Transactional email helpers (LAB-49 Phase 4.5, API2 A2-7 / API10 G10-6).

The password-reset link is the one email that is a security control: if it is
not delivered, users are locked out and the reset flow silently fails. The raw
token is passed straight to the renderer and only ever lives in that message;
it is never logged or stored.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def reset_link(request: Any, raw_token: str) -> str:
    base = str(getattr(settings, "FRONTEND_BASE_URL", "") or "").rstrip("/")
    if not base:
        scheme = "https" if request.is_secure() else "http"
        base = f"{scheme}://{request.get_host()}"
    path = str(getattr(settings, "FRONTEND_RESET_PATH", "/reset-password"))
    return f"{base}{path}?{urlencode({'token': raw_token})}"


def send_password_reset_email_to(email: str, display_name: str, link: str) -> bool:
    """Send exactly one working reset link to an explicit address."""
    subject = "Reset your LabFlow password"
    body = (
        f"Hello {display_name or email},\n\n"
        "Use the link below to reset your LabFlow password. It expires in "
        "60 minutes and can be used once:\n\n"
        f"{link}\n\n"
        "If you did not request this, you can ignore this email.\n"
    )
    try:
        send_mail(
            subject,
            body,
            str(getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@labflow.app")),
            [email],
            fail_silently=False,
        )
        return True
    except Exception as exc:  # pragma: no cover - provider outage
        logger.error("Password-reset email delivery failed: %s", exc)
        return False


def send_password_reset_email(request: Any, user: Any, raw_token: str) -> bool:
    """Send exactly one working reset link; never raise into the 202 path."""
    return send_password_reset_email_to(
        user.email, user.display_name or "", reset_link(request, raw_token)
    )
