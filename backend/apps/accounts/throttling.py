"""Redis-based login throttling per Doc 08 §10.1 & §10.3.

Rules:
- 5 attempts / 15 min per (tenant, email)
- 20 attempts / 15 min per (tenant, IP)
- Fail closed: if Redis is unavailable, raises ThrottleServiceUnavailable (answers 503)
- Fixed windows expiring at window end
"""

import time
from typing import Final

from django.core.cache import cache

LOGIN_WINDOW_SECONDS: Final[int] = 15 * 60  # 15 minutes (900s)
MAX_LOGIN_ATTEMPTS_PER_EMAIL: Final[int] = 5
MAX_LOGIN_ATTEMPTS_PER_IP: Final[int] = 20


class ThrottleServiceUnavailable(Exception):
    """Raised when Redis fails during auth throttling (Doc 08 §10.3 fail-closed)."""


def _get_retry_after(window_start: float, window_seconds: int) -> int:
    elapsed = time.time() - window_start
    remaining = window_seconds - elapsed
    return max(1, int(remaining))


def check_and_record_login_throttle(
    tenant_id: str,
    email: str,
    ip: str,
) -> tuple[bool, int]:
    """Check login attempt limits and increment counters atomically.

    Returns (is_throttled, retry_after_seconds).
    Raises ThrottleServiceUnavailable if cache operations fail.
    """
    clean_email = email.strip().lower()
    clean_ip = ip.strip() if ip else "unknown_ip"

    email_key = f"auth:throttle:login:email:{tenant_id}:{clean_email}"
    ip_key = f"auth:throttle:login:ip:{tenant_id}:{clean_ip}"
    time_email_key = f"{email_key}:start"
    time_ip_key = f"{ip_key}:start"

    try:
        now = time.time()

        # 1. Email throttle
        email_count = cache.get(email_key)
        if email_count is not None and int(email_count) >= MAX_LOGIN_ATTEMPTS_PER_EMAIL:
            start_time = float(cache.get(time_email_key) or now)
            return True, _get_retry_after(start_time, LOGIN_WINDOW_SECONDS)

        # 2. IP throttle
        ip_count = cache.get(ip_key)
        if ip_count is not None and int(ip_count) >= MAX_LOGIN_ATTEMPTS_PER_IP:
            start_time = float(cache.get(time_ip_key) or now)
            return True, _get_retry_after(start_time, LOGIN_WINDOW_SECONDS)

        # Increment email counter
        if email_count is None:
            cache.set(email_key, 1, timeout=LOGIN_WINDOW_SECONDS)
            cache.set(time_email_key, now, timeout=LOGIN_WINDOW_SECONDS)
        else:
            try:
                cache.incr(email_key)
            except ValueError:
                cache.set(email_key, int(email_count) + 1, timeout=LOGIN_WINDOW_SECONDS)

        # Increment IP counter
        if ip_count is None:
            cache.set(ip_key, 1, timeout=LOGIN_WINDOW_SECONDS)
            cache.set(time_ip_key, now, timeout=LOGIN_WINDOW_SECONDS)
        else:
            try:
                cache.incr(ip_key)
            except ValueError:
                cache.set(ip_key, int(ip_count) + 1, timeout=LOGIN_WINDOW_SECONDS)

        return False, 0

    except Exception as exc:
        raise ThrottleServiceUnavailable(
            f"Auth throttle failed closed on Redis error: {exc}"
        ) from exc
