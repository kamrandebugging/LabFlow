"""Platform Redis session registry (Doc 08 §4.3, §4.6).

Mirrors accounts/session_registry.py but uses platform-scoped keys:
  platform:sessions:<user_id>  (no tenant_id — platform users are global)
  platform:denylist:jti:used:<jti>
  platform:denylist:jti:revoked:<jti>
  platform:denylist:jti:access:<jti>
  platform:revoked:session:<session_id>
  platform:revoked_before:<user_id>
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Final

from django.core.cache import cache

logger = logging.getLogger(__name__)

SEVEN_DAYS_SECONDS: Final[int] = 7 * 86400
FIFTEEN_MINUTES_SECONDS: Final[int] = 900


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


def _sessions_key(user_id: uuid.UUID | str) -> str:
    return f"platform:sessions:{user_id}"


def _revocation_marker_key(user_id: uuid.UUID | str) -> str:
    return f"platform:revoked_before:{user_id}"


def _used_jti_key(jti: str) -> str:
    return f"platform:denylist:jti:used:{jti}"


def _revoked_jti_key(jti: str) -> str:
    return f"platform:denylist:jti:revoked:{jti}"


def _paired_access_jti_key(jti: str) -> str:
    return f"platform:denylist:jti:access:{jti}"


def _revoked_session_key(session_id: uuid.UUID | str) -> str:
    return f"platform:revoked:session:{session_id}"


# ---------------------------------------------------------------------------
# Session revocation markers
# ---------------------------------------------------------------------------


def platform_mark_session_revoked(
    session_id: uuid.UUID | str, ttl_seconds: int = SEVEN_DAYS_SECONDS
) -> None:
    try:
        cache.set(_revoked_session_key(session_id), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to mark platform session revoked in Redis: %s", exc)


def platform_is_session_revoked(session_id: uuid.UUID | str) -> bool:
    try:
        return cache.get(_revoked_session_key(session_id)) is not None
    except Exception as exc:
        logger.warning("Failed to check if platform session revoked in Redis: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------


def platform_register_session(
    user_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
    fid: uuid.UUID | str,
    refresh_jti: str,
    ip: str,
    user_agent: str,
    family_expires_at: int,
) -> dict[str, Any]:
    """Register a new platform session in Redis."""
    key = _sessions_key(user_id)
    now_iso = datetime.now(UTC).isoformat()

    session_data: dict[str, Any] = {
        "id": str(session_id),
        "fid": str(fid),
        "current_refresh_jti": refresh_jti,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": now_iso,
        "last_active": now_iso,
        "family_expires_at": family_expires_at,
    }

    try:
        raw = cache.get(key)
        sessions: dict[str, Any] = json.loads(raw) if raw else {}
        sessions[str(session_id)] = session_data
        cache.set(key, json.dumps(sessions), timeout=SEVEN_DAYS_SECONDS)
    except Exception as exc:
        logger.warning("Failed to register platform session in Redis: %s", exc)

    return session_data


def platform_get_active_sessions(user_id: uuid.UUID | str) -> list[dict[str, Any]]:
    """Return all active sessions for a platform user."""
    key = _sessions_key(user_id)
    try:
        raw = cache.get(key)
        if not raw:
            return []
        sessions: dict[str, Any] = json.loads(raw)
        return list(sessions.values())
    except Exception as exc:
        logger.warning("Failed to fetch platform sessions from Redis: %s", exc)
        return []


def platform_update_session_refresh_jti(
    user_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
    new_refresh_jti: str,
) -> None:
    key = _sessions_key(user_id)
    try:
        raw = cache.get(key)
        if not raw:
            return
        sessions: dict[str, Any] = json.loads(raw)
        sid = str(session_id)
        if sid in sessions:
            sessions[sid]["current_refresh_jti"] = new_refresh_jti
            sessions[sid]["last_active"] = datetime.now(UTC).isoformat()
            cache.set(key, json.dumps(sessions), timeout=SEVEN_DAYS_SECONDS)
    except Exception as exc:
        logger.warning("Failed to update platform session jti in Redis: %s", exc)


def platform_delete_session(
    user_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
) -> dict[str, Any] | None:
    key = _sessions_key(user_id)
    try:
        raw = cache.get(key)
        if not raw:
            return None
        sessions: dict[str, Any] = json.loads(raw)
        sid = str(session_id)
        if sid in sessions:
            deleted = sessions.pop(sid)
            cache.set(key, json.dumps(sessions), timeout=SEVEN_DAYS_SECONDS)
            platform_mark_session_revoked(sid)
            return deleted
        return None
    except Exception as exc:
        logger.warning("Failed to delete platform session from Redis: %s", exc)
        return None


def platform_clear_all_sessions(
    user_id: uuid.UUID | str,
    except_session_id: uuid.UUID | str | None = None,
) -> list[dict[str, Any]]:
    """Remove all sessions for a platform user, optionally keeping one."""
    key = _sessions_key(user_id)
    try:
        raw = cache.get(key)
        if not raw:
            return []
        sessions: dict[str, Any] = json.loads(raw)
        removed: list[dict[str, Any]] = []

        if except_session_id:
            kept: dict[str, Any] = {}
            for sid, sdata in sessions.items():
                if sid == str(except_session_id):
                    kept[sid] = sdata
                else:
                    removed.append(sdata)
                    platform_mark_session_revoked(sid)
                    if "current_refresh_jti" in sdata:
                        platform_denylist_jti(sdata["current_refresh_jti"])
            cache.set(key, json.dumps(kept), timeout=SEVEN_DAYS_SECONDS)
        else:
            removed = list(sessions.values())
            for sdata in removed:
                platform_mark_session_revoked(sdata["id"])
                if "current_refresh_jti" in sdata:
                    platform_denylist_jti(sdata["current_refresh_jti"])
            cache.delete(key)

        return removed
    except Exception as exc:
        logger.warning("Failed to clear platform sessions from Redis: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Token denylist
# ---------------------------------------------------------------------------


def platform_mark_jti_used(jti: str, ttl_seconds: int = SEVEN_DAYS_SECONDS) -> None:
    try:
        cache.set(_used_jti_key(jti), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to mark platform jti used in Redis: %s", exc)


def platform_is_jti_used(jti: str) -> bool:
    try:
        return cache.get(_used_jti_key(jti)) is not None
    except Exception as exc:
        logger.warning("Failed to check platform jti used in Redis: %s", exc)
        return False


def platform_denylist_jti(jti: str, ttl_seconds: int = SEVEN_DAYS_SECONDS) -> None:
    try:
        cache.set(_revoked_jti_key(jti), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to denylist platform jti in Redis: %s", exc)


def platform_is_jti_denylisted(jti: str) -> bool:
    try:
        return cache.get(_revoked_jti_key(jti)) is not None
    except Exception as exc:
        logger.warning("Failed to check platform jti denylisted in Redis: %s", exc)
        return False


def platform_denylist_access_jti(
    jti: str, ttl_seconds: int = FIFTEEN_MINUTES_SECONDS
) -> None:
    try:
        cache.set(_paired_access_jti_key(jti), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to denylist platform access jti in Redis: %s", exc)


def platform_is_access_jti_denylisted(jti: str) -> bool:
    try:
        return cache.get(_paired_access_jti_key(jti)) is not None
    except Exception as exc:
        logger.warning(
            "Failed to check platform access jti denylisted in Redis: %s", exc
        )
        return False


def platform_set_revocation_marker(
    user_id: uuid.UUID | str,
    timestamp: float | None = None,
) -> None:
    ts = timestamp or time.time()
    try:
        cache.set(_revocation_marker_key(user_id), str(ts), timeout=SEVEN_DAYS_SECONDS)
    except Exception as exc:
        logger.warning("Failed to set platform revocation marker in Redis: %s", exc)


def platform_get_revocation_marker(user_id: uuid.UUID | str) -> float | None:
    try:
        val = cache.get(_revocation_marker_key(user_id))
        if val is None:
            return None
        return float(val)
    except Exception as exc:
        logger.warning("Failed to read platform revocation marker from Redis: %s", exc)
        return None
