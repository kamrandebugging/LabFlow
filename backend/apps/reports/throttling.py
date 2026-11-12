"""Per-IP rate limiting for the public report-portal endpoints
(KAN-156 / LAB-31; ticket title requirement).

Minimal fixed-window counter on the Django cache (60 req/min/IP by
default, settings REPORT_ACCESS_RATE_LIMIT_PER_MINUTE). No existing
throttle pattern in the repo — this module is the pattern.

Design notes:
- The throttle runs BEFORE the argon2 hash scan, so an attacker cannot
  turn the ~100ms-per-row verify cost into a cheap DoS.
- Fail-open on cache errors: a down cache must not 500 patients; the
  failure is logged. The trade-off is documented here rather than hidden.
- The fixed window uses atomic cache.add (SET NX + TTL) for the first
  hit, so concurrent first-hits cannot double-count and the window
  always expires on every cache backend.
- XFF spoofing caveat: see get_client_ip — prod must set trusted_proxies
  on the edge proxy or a client can rotate fake XFF values to dodge the
  per-IP budget.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework.request import Request

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW_SECONDS = 60


def get_client_ip(request: Request) -> str:
    """Best-effort client IP (X-Forwarded-For aware).

    Caddy appends the real peer to XFF; the **last** hop is the trusted one.
    Taking the leftmost value would accept a client-supplied spoof.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def public_rate_limit_exceeded(request: Request, scope: str) -> bool:
    """Return True when this IP exceeded its fixed-window budget for scope.

    Scopes: "report_access" (GET /api/v1/report-access/{token}),
    "report_file" (GET /api/v1/report-files/<sig>/).
    """
    limit = int(getattr(settings, "REPORT_ACCESS_RATE_LIMIT_PER_MINUTE", 60))
    key = f"labflow:rl:{scope}:{get_client_ip(request)}"
    try:
        # Atomic first-hit (SET NX with TTL): the window always expires,
        # even on backends where incr() creates keys without a TTL (redis).
        if cache.add(key, 1, timeout=RATE_LIMIT_WINDOW_SECONDS):
            return False  # fresh window: first request is always allowed
        try:
            count = cache.incr(key)
        except ValueError:
            # Non-numeric value (should not happen): reset the window.
            cache.set(key, 1, timeout=RATE_LIMIT_WINDOW_SECONDS)
            return False
        return count > limit
    except Exception:
        logger.warning(
            "report-portal throttle cache error; allowing request", exc_info=True
        )
        return False


def _fixed_window(key: str, limit: int, window_seconds: int) -> bool:
    """True when the counter for ``key`` exceeded ``limit``."""
    try:
        if cache.add(key, 1, timeout=window_seconds):
            return False
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window_seconds)
            return False
        return count > limit
    except Exception:
        logger.warning("report token throttle cache error", exc_info=True)
        return False


def report_token_rate_limit_exceeded(token: str) -> bool:
    """60 per 10 minutes per report access token (API6 A6-4)."""
    import hashlib

    digest = hashlib.sha256((token or "").encode()).hexdigest()[:32]
    limit = int(getattr(settings, "REPORT_TOKEN_RATE_LIMIT_PER_10MIN", 60))
    return _fixed_window(f"labflow:rl:report_token:{digest}", limit, 10 * 60)


def record_invalid_report_token(request: Request) -> bool:
    """20 invalid-token attempts/hour/IP; True when the budget is exhausted."""
    limit = int(getattr(settings, "REPORT_INVALID_TOKEN_PER_HOUR", 20))
    key = f"labflow:rl:report_invalid:{get_client_ip(request)}"
    return _fixed_window(key, limit, 60 * 60)
