"""Redis-based login throttling per Doc 08 §10.1 & §10.3.

Rules:
- 5 attempts / 15 min per (tenant, email)
- 20 attempts / 15 min per (tenant, IP)
- Fail closed: if Redis is unavailable, raises ThrottleServiceUnavailable (answers 503)
- Fixed windows expiring at window end
"""

import logging
import time
from typing import Final

from django.core.cache import cache

logger = logging.getLogger(__name__)

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


def reset_login_throttle(tenant_id: str, email: str, ip: str) -> None:
    """Clear the failed-login counters after a correct password.

    Counters are incremented before authentication (fail-closed and race-safe),
    so a successful sign-in must clear them; otherwise five legitimate logins
    inside the 15-minute window would lock the account out.
    """
    clean_email = email.strip().lower()
    clean_ip = ip.strip() if ip else "unknown_ip"
    email_key = f"auth:throttle:login:email:{tenant_id}:{clean_email}"
    ip_key = f"auth:throttle:login:ip:{tenant_id}:{clean_ip}"
    for key in (email_key, f"{email_key}:start", ip_key, f"{ip_key}:start"):
        try:
            cache.delete(key)
        except Exception:
            # Throttling must never block an otherwise valid login.
            logger.warning("Failed to reset login throttle key %s", key)


PASSWORD_RESET_WINDOW_SECONDS: Final[int] = 60 * 60  # 1 hour (3600s)
MAX_PASSWORD_RESET_ATTEMPTS_PER_EMAIL: Final[int] = 3
MAX_PASSWORD_RESET_ATTEMPTS_PER_IP: Final[int] = 10


def check_and_record_password_reset_throttle(
    tenant_id: str,
    email: str,
    ip: str,
) -> tuple[bool, int]:
    """Check password reset request limits and increment counters atomically.

    Doc 08 §10.1 & §10.3:
    - 3 attempts / hour per (tenant, email)
    - 10 attempts / hour per (tenant, IP)
    - Fails closed silently on Redis outage (returns True, 3600).
    Returns (is_throttled, retry_after_seconds).
    """
    clean_email = email.strip().lower()
    clean_ip = ip.strip() if ip else "unknown_ip"

    email_key = f"auth:throttle:reset:email:{tenant_id}:{clean_email}"
    ip_key = f"auth:throttle:reset:ip:{tenant_id}:{clean_ip}"
    time_email_key = f"{email_key}:start"
    time_ip_key = f"{ip_key}:start"

    try:
        now = time.time()

        # 1. Email throttle
        email_count = cache.get(email_key)
        if (
            email_count is not None
            and int(email_count) >= MAX_PASSWORD_RESET_ATTEMPTS_PER_EMAIL
        ):
            start_time = float(cache.get(time_email_key) or now)
            return True, _get_retry_after(start_time, PASSWORD_RESET_WINDOW_SECONDS)

        # 2. IP throttle
        ip_count = cache.get(ip_key)
        if ip_count is not None and int(ip_count) >= MAX_PASSWORD_RESET_ATTEMPTS_PER_IP:
            start_time = float(cache.get(time_ip_key) or now)
            return True, _get_retry_after(start_time, PASSWORD_RESET_WINDOW_SECONDS)

        # Increment email counter
        if email_count is None:
            cache.set(email_key, 1, timeout=PASSWORD_RESET_WINDOW_SECONDS)
            cache.set(time_email_key, now, timeout=PASSWORD_RESET_WINDOW_SECONDS)
        else:
            try:
                cache.incr(email_key)
            except ValueError:
                cache.set(
                    email_key,
                    int(email_count) + 1,
                    timeout=PASSWORD_RESET_WINDOW_SECONDS,
                )

        # Increment IP counter
        if ip_count is None:
            cache.set(ip_key, 1, timeout=PASSWORD_RESET_WINDOW_SECONDS)
            cache.set(time_ip_key, now, timeout=PASSWORD_RESET_WINDOW_SECONDS)
        else:
            try:
                cache.incr(ip_key)
            except ValueError:
                cache.set(
                    ip_key,
                    int(ip_count) + 1,
                    timeout=PASSWORD_RESET_WINDOW_SECONDS,
                )

        return False, 0

    except Exception:
        # Doc 08 §10.1: Invisible fail-closed on Redis outage
        return True, PASSWORD_RESET_WINDOW_SECONDS


def check_and_record_generic_throttle(
    key_prefix: str,
    identifier: str,
    max_attempts: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """Generic atomic sliding/fixed window throttle.

    Returns (is_throttled, retry_after_seconds).
    Fails closed silently on Redis outage.
    """
    key = f"{key_prefix}:{identifier}"
    time_key = f"{key}:start"
    try:
        now = time.time()
        current_count = cache.get(key)
        if current_count is not None and int(current_count) >= max_attempts:
            start_time = float(cache.get(time_key) or now)
            return True, _get_retry_after(start_time, window_seconds)

        if current_count is None:
            cache.set(key, 1, timeout=window_seconds)
            cache.set(time_key, now, timeout=window_seconds)
        else:
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, int(current_count) + 1, timeout=window_seconds)

        return False, 0
    except Exception:
        return True, window_seconds
