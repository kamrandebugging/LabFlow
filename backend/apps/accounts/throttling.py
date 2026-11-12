"""Redis-based login throttling per Doc 08 §10.1 & §10.3.

Rules:
- 5 attempts / 15 min per (tenant, email)
- 20 attempts / 15 min per (tenant, IP)
- Fail closed: if Redis is unavailable, raises ThrottleServiceUnavailable (answers 503)
- Fixed windows expiring at window end
"""

import logging
import time
import uuid
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


# ---------------------------------------------------------------------------
# Progressive account lockout (LAB-49 Phase 5.6, SE-25)
# ---------------------------------------------------------------------------


def _lockout_key(tenant_id: str, email: str, ip: str = "") -> str:
    return f"auth:lockout:{tenant_id}:{ip}:{email.strip().lower()}"


def _violation_key(tenant_id: str, email: str, ip: str = "") -> str:
    return f"auth:lockout:violations:{tenant_id}:{ip}:{email.strip().lower()}"


def check_account_lockout(tenant_id: str, email: str, ip: str = "") -> tuple[bool, int]:
    """Return (is_locked, retry_after_seconds).

    Keyed per (tenant, email, IP) so an attacker cannot lock a victim out
    from a different address (django-reviewer 2026-11-12).
    """
    try:
        ttl = cache.get(_lockout_key(tenant_id, email, ip))
        if ttl is not None:
            return True, max(1, int(ttl))
    except Exception:
        # Fail closed: an unreadable lock state must not unlock accounts.
        return True, 60
    return False, 0


def record_throttle_violation(tenant_id: str, email: str, ip: str = "") -> bool:
    """Count a throttled login window; lock the account after N windows.

    Returns True when this call engaged the lock. The lock is a Redis TTL
    value; an Owner can clear it with ``manage.py unlock_account``.
    """
    from django.conf import settings

    threshold = int(getattr(settings, "ACCOUNT_LOCKOUT_THRESHOLD", 3))
    lock_seconds = int(getattr(settings, "ACCOUNT_LOCKOUT_SECONDS", 3600))
    vkey = _violation_key(tenant_id, email, ip)
    try:
        # Count at most once per 15-minute throttle window, so a burst of
        # retries inside one window cannot fast-forward the lock.
        import time

        window_id = int(time.time() // LOGIN_WINDOW_SECONDS)
        if not cache.add(f"{vkey}:window:{window_id}", "1", timeout=lock_seconds):
            return False
        count = cache.get(vkey)
        count = int(count or 0) + 1
        cache.set(vkey, count, timeout=lock_seconds)
        if count < threshold:
            return False
        cache.set(
            _lockout_key(tenant_id, email, ip), lock_seconds, timeout=lock_seconds
        )
    except Exception:
        # Cache outage during violation counting: keep the throttle closed but
        # do not claim a lock we cannot store.
        return False
    try:
        from apps.accounts.models import AuditLog, StaffUser

        target = StaffUser.objects.filter(email=email.strip().lower()).first()
        AuditLog.objects.create(
            actor_id=None,
            action="auth.account_locked",
            entity_type="staff_user",
            entity_id=target.id if target else uuid.uuid4(),
            before_jsonb=None,
            after_jsonb={
                "email": email.strip().lower(),
                "throttled_windows": count,
                "lock_seconds": lock_seconds,
            },
            ip=None,
            user_agent="login_throttle",
        )
    except Exception:
        pass
    return True


def unlock_account(tenant_id: str, email: str, ip: str = "") -> None:
    """Clear the lock and violation counter for this email+IP."""
    for key in (
        _lockout_key(tenant_id, email, ip),
        _violation_key(tenant_id, email, ip),
    ):
        try:
            cache.delete(key)
        except Exception:
            logger.warning("Failed to clear lockout key %s", key)
