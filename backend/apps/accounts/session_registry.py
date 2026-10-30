"""Redis Session Registry & Token Denylist per Doc 08 §4.3, §4.6, §4.7.

Manages:
- Active sessions per staff user (auth:sessions:<tenant_id>:<user_id>)
- Token denylist (used refresh jtis, revoked refresh jtis, paired access jtis)
- Revocation marker (auth:revoked_before:<staff_user_id>)
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


def _sessions_key(tenant_id: str, user_id: uuid.UUID | str) -> str:
    return f"auth:sessions:{tenant_id}:{user_id}"


def _revocation_marker_key(user_id: uuid.UUID | str) -> str:
    return f"auth:revoked_before:{user_id}"


def _used_jti_key(jti: str) -> str:
    return f"auth:denylist:jti:used:{jti}"


def _revoked_jti_key(jti: str) -> str:
    return f"auth:denylist:jti:revoked:{jti}"


def _paired_access_jti_key(jti: str) -> str:
    return f"auth:denylist:jti:access:{jti}"


def _revoked_session_key(session_id: uuid.UUID | str) -> str:
    return f"auth:revoked:session:{session_id}"


def mark_session_revoked(
    session_id: uuid.UUID | str, ttl_seconds: int = SEVEN_DAYS_SECONDS
) -> None:
    """Mark a session revoked in Redis."""
    try:
        cache.set(_revoked_session_key(session_id), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to mark session revoked in Redis: %s", exc)


def is_session_revoked(session_id: uuid.UUID | str) -> bool:
    """Check if session has been explicitly revoked."""
    try:
        return cache.get(_revoked_session_key(session_id)) is not None
    except Exception as exc:
        logger.warning("Failed to check if session revoked in Redis: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Session Registry Operations
# ---------------------------------------------------------------------------


def register_session(
    tenant_id: str,
    user_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
    fid: uuid.UUID | str,
    refresh_jti: str,
    ip: str,
    user_agent: str,
    family_expires_at: int,
) -> dict[str, Any]:
    """Register a new active session under the user's registry."""
    key = _sessions_key(tenant_id, user_id)
    now_iso = datetime.now(UTC).isoformat()

    session_data = {
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
        # Registry TTL matches the 7-day max family cap
        cache.set(key, json.dumps(sessions), timeout=SEVEN_DAYS_SECONDS)
    except Exception as exc:
        logger.warning("Failed to register session in Redis: %s", exc)

    return session_data


def get_active_sessions(
    tenant_id: str,
    user_id: uuid.UUID | str,
) -> list[dict[str, Any]]:
    """Return list of active sessions for a staff user."""
    key = _sessions_key(tenant_id, user_id)
    try:
        raw = cache.get(key)
        if not raw:
            return []
        sessions: dict[str, Any] = json.loads(raw)
        return list(sessions.values())
    except Exception as exc:
        logger.warning("Failed to fetch sessions from Redis: %s", exc)
        return []


def update_session_refresh_jti(
    tenant_id: str,
    user_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
    new_refresh_jti: str,
) -> None:
    """Update current refresh jti and last_active for a session after rotation."""
    key = _sessions_key(tenant_id, user_id)
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
        logger.warning("Failed to update session jti in Redis: %s", exc)


def delete_session(
    tenant_id: str,
    user_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
) -> dict[str, Any] | None:
    """Delete a single session scoped to (tenant_id, user_id, session_id).

    Returns the deleted session data if found, else None.
    """
    key = _sessions_key(tenant_id, user_id)
    try:
        raw = cache.get(key)
        if not raw:
            return None
        sessions: dict[str, Any] = json.loads(raw)
        sid = str(session_id)
        if sid in sessions:
            deleted = sessions.pop(sid)
            cache.set(key, json.dumps(sessions), timeout=SEVEN_DAYS_SECONDS)
            mark_session_revoked(sid)
            return deleted
        return None
    except Exception as exc:
        logger.warning("Failed to delete session from Redis: %s", exc)
        return None


def clear_all_user_sessions(
    tenant_id: str,
    user_id: uuid.UUID | str,
    except_session_id: uuid.UUID | str | None = None,
) -> list[dict[str, Any]]:
    """Remove all sessions for a user, optionally preserving except_session_id."""
    key = _sessions_key(tenant_id, user_id)
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
                    mark_session_revoked(sid)
                    if "current_refresh_jti" in sdata:
                        denylist_jti(sdata["current_refresh_jti"])
            cache.set(key, json.dumps(kept), timeout=SEVEN_DAYS_SECONDS)
        else:
            removed = list(sessions.values())
            for sdata in removed:
                mark_session_revoked(sdata["id"])
                if "current_refresh_jti" in sdata:
                    denylist_jti(sdata["current_refresh_jti"])
            cache.delete(key)

        return removed
    except Exception as exc:
        logger.warning("Failed to clear sessions from Redis: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Token Denylist & Revocation Marker
# ---------------------------------------------------------------------------


def mark_jti_used(jti: str, ttl_seconds: int = SEVEN_DAYS_SECONDS) -> None:
    """Mark a rotated refresh token's jti as used (Doc 08 §4.3)."""
    try:
        cache.set(_used_jti_key(jti), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to mark jti used in Redis: %s", exc)


def is_jti_used(jti: str) -> bool:
    """Check if refresh token jti was already rotated (reuse detection)."""
    try:
        return cache.get(_used_jti_key(jti)) is not None
    except Exception as exc:
        logger.warning("Failed to check if jti used in Redis: %s", exc)
        return False


def denylist_jti(jti: str, ttl_seconds: int = SEVEN_DAYS_SECONDS) -> None:
    """Denylist a revoked refresh token jti."""
    try:
        cache.set(_revoked_jti_key(jti), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to denylist jti in Redis: %s", exc)


def is_jti_denylisted(jti: str) -> bool:
    """Check if token jti was explicitly revoked."""
    try:
        return cache.get(_revoked_jti_key(jti)) is not None
    except Exception as exc:
        logger.warning("Failed to check if jti denylisted in Redis: %s", exc)
        return False


def denylist_access_jti(jti: str, ttl_seconds: int = FIFTEEN_MINUTES_SECONDS) -> None:
    """Denylist paired access token jti on logout (SE-07 instant logout)."""
    try:
        cache.set(_paired_access_jti_key(jti), "1", timeout=max(1, ttl_seconds))
    except Exception as exc:
        logger.warning("Failed to denylist access jti in Redis: %s", exc)


def is_access_jti_denylisted(jti: str) -> bool:
    """Check if access token jti is denylisted."""
    try:
        return cache.get(_paired_access_jti_key(jti)) is not None
    except Exception as exc:
        logger.warning("Failed to check if access jti denylisted in Redis: %s", exc)
        return False


def set_user_revocation_marker(
    user_id: uuid.UUID | str,
    timestamp: float | None = None,
) -> None:
    """Set auth:revoked_before:<staff_user_id> to timestamp (Doc 08 §4.6)."""
    ts = timestamp or time.time()
    key = _revocation_marker_key(user_id)
    try:
        cache.set(key, str(ts), timeout=SEVEN_DAYS_SECONDS)
    except Exception as exc:
        logger.warning("Failed to set revocation marker in Redis: %s", exc)


def get_user_revocation_marker(user_id: uuid.UUID | str) -> float | None:
    """Return timestamp before which all issued tokens are revoked."""
    key = _revocation_marker_key(user_id)
    try:
        val = cache.get(key)
        if val is None:
            return None
        return float(val)
    except Exception as exc:
        logger.warning("Failed to read revocation marker from Redis: %s", exc)
        return None
