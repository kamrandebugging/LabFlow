"""Platform (Super Admin) authentication engine — Doc 08 §4, Doc 04 §12.1.

Mirrors ``apps.accounts.auth_service`` with ``PlatformUser`` as the subject:

- HS256 access tokens (15 min) and refresh tokens (7 days, family bound).
- Redis-only denylist: used refresh jtis, revoked jtis, paired access jtis.
- Rotation-on-use with reuse detection that revokes every session.
- TOTP enrolment/verification with a Fernet-encrypted secret.
- Password reset with a 32-byte token whose argon2 hash is the only stored
  artefact.
- Every state change writes exactly one ``platform_audit`` row in the same
  transaction as the change.

Secrets (TOTP secret, backup codes, raw reset tokens) never reach an audit
row, a log line or an alert payload.
"""

import json
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.models import PlatformAudit, PlatformPasswordResetToken, PlatformUser
from apps.platform.platform_jwt import (
    PLATFORM_ACCESS_LIFETIME_SECONDS,
    PLATFORM_REFRESH_LIFETIME_SECONDS,
    platform_decode_jwt,
    platform_mint_access_token,
    platform_mint_refresh_token,
)
from apps.platform.platform_session_registry import (
    platform_clear_all_sessions,
    platform_delete_session,
    platform_denylist_access_jti,
    platform_denylist_jti,
    platform_get_active_sessions,
    platform_get_revocation_marker,
    platform_is_access_jti_denylisted,
    platform_is_jti_denylisted,
    platform_is_jti_used,
    platform_is_session_revoked,
    platform_mark_jti_used,
    platform_mark_session_revoked,
    platform_register_session,
    platform_set_revocation_marker,
    platform_update_session_refresh_jti,
)

logger = logging.getLogger(__name__)

PLATFORM_ROLE: Final[str] = "super_admin"
GENERIC_INVALID_CREDENTIALS: Final[str] = "invalid_credentials"

#: Precomputed hash so an unknown email costs the same as a wrong password.
DUMMY_PASSWORD_HASH: Final[str] = make_password(
    "dummy-constant-time-platform-protection"
)

CHALLENGE_TTL_SECONDS: Final[int] = 300
CHALLENGE_MAX_ATTEMPTS: Final[int] = 5
ENROLLMENT_TTL_SECONDS: Final[int] = 900
PASSWORD_RESET_TTL_SECONDS: Final[int] = 3600
BACKUP_CODE_COUNT: Final[int] = 10

LOGIN_WINDOW_SECONDS: Final[int] = 15 * 60
MAX_LOGIN_ATTEMPTS_PER_EMAIL: Final[int] = 5
MAX_LOGIN_ATTEMPTS_PER_IP: Final[int] = 20
RESET_WINDOW_SECONDS: Final[int] = 60 * 60
MAX_RESET_ATTEMPTS_PER_EMAIL: Final[int] = 3
MAX_RESET_ATTEMPTS_PER_IP: Final[int] = 10


class PlatformAuthUnavailable(Exception):
    """Raised when Redis is unreachable during auth (fail closed → 503)."""


class PlatformTokenInvalid(Exception):
    """Raised when a password reset token is invalid, expired or consumed."""


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


def capture_security_alert(message: str, **context: Any) -> None:
    """Emit a structured error log and forward to Sentry when available.

    Context must never carry secrets: callers pass ids and reasons only.
    """
    logger.error(
        json.dumps(
            {"event": "platform_security_alert", "message": message, **context},
            sort_keys=True,
            default=str,
        )
    )
    try:
        import sentry_sdk
    except ImportError:
        return
    try:
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level="error")
    except Exception:  # pragma: no cover - defence against SDK failures
        logger.warning("Sentry capture failed for platform security alert")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def write_platform_audit(
    *,
    action: str,
    entity_type: str = "platform_user",
    entity_id: uuid.UUID | None,
    actor_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> PlatformAudit:
    """Insert one immutable ``platform_audit`` row (Doc 02 §4.1)."""
    return PlatformAudit.objects.create(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_jsonb=before,
        after_jsonb=after,
        ip=ip,
        user_agent=user_agent,
    )


# ---------------------------------------------------------------------------
# Throttling (fail closed)
# ---------------------------------------------------------------------------


def _retry_after(start: float, window: int) -> int:
    return max(1, int(window - (time.time() - start)))


def _consume(bucket: str, window: int, limit: int, now: float) -> bool:
    """Increment ``bucket``; return True when the caller is over the limit."""
    count = cache.get(bucket)
    if count is not None and int(count) >= limit:
        return True
    if count is None:
        cache.set(bucket, 1, timeout=window)
        cache.set(f"{bucket}:start", now, timeout=window)
    else:
        try:
            cache.incr(bucket)
        except ValueError:
            cache.set(bucket, int(count) + 1, timeout=window)
    return False


def check_and_record_platform_login_throttle(email: str, ip: str) -> tuple[bool, int]:
    """5 attempts / 15 min per email, 20 / 15 min per IP (Doc 08 §10.1).

    Returns ``(is_throttled, retry_after_seconds)``. Raises
    :class:`PlatformAuthUnavailable` when Redis fails (fail closed).
    """
    clean_email = email.strip().lower()
    clean_ip = (ip or "unknown_ip").strip() or "unknown_ip"
    email_key = f"platform:throttle:login:email:{clean_email}"
    ip_key = f"platform:throttle:login:ip:{clean_ip}"
    try:
        now = time.time()
        if _consume(email_key, LOGIN_WINDOW_SECONDS, MAX_LOGIN_ATTEMPTS_PER_EMAIL, now):
            start = float(cache.get(f"{email_key}:start") or now)
            return True, _retry_after(start, LOGIN_WINDOW_SECONDS)
        if _consume(ip_key, LOGIN_WINDOW_SECONDS, MAX_LOGIN_ATTEMPTS_PER_IP, now):
            start = float(cache.get(f"{ip_key}:start") or now)
            return True, _retry_after(start, LOGIN_WINDOW_SECONDS)
        return False, 0
    except Exception as exc:
        raise PlatformAuthUnavailable(
            f"Platform login throttle failed closed: {exc}"
        ) from exc


def check_and_record_platform_reset_throttle(email: str, ip: str) -> bool:
    """3 reset requests / hour per email, 10 / hour per IP.

    Returns True when throttled. Fails closed (throttled) on Redis errors so
    the endpoint keeps answering its constant ``202``.
    """
    clean_email = email.strip().lower()
    clean_ip = (ip or "unknown_ip").strip() or "unknown_ip"
    email_key = f"platform:throttle:reset:email:{clean_email}"
    ip_key = f"platform:throttle:reset:ip:{clean_ip}"
    try:
        now = time.time()
        if _consume(email_key, RESET_WINDOW_SECONDS, MAX_RESET_ATTEMPTS_PER_EMAIL, now):
            return True
        return _consume(ip_key, RESET_WINDOW_SECONDS, MAX_RESET_ATTEMPTS_PER_IP, now)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------


def validate_platform_password(
    password: str, email: str
) -> tuple[bool, str | None, str | None]:
    """Validate against the shared tenant policy (12–128, blocklist, argon2id)."""
    from apps.accounts.password_policy import validate_password_policy

    return validate_password_policy(password=password, user_email=email)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PlatformAuthService:
    """Platform operator authentication, sessions and TOTP."""

    # -- helpers ----------------------------------------------------------

    @classmethod
    def _fernet(cls) -> Fernet:
        key = getattr(settings, "LABFLOW_TOTP_ENCRYPTION_KEY", None)
        if not key:
            raise RuntimeError("LABFLOW_TOTP_ENCRYPTION_KEY is not configured")
        raw = key.encode() if isinstance(key, str) else key
        return Fernet(raw)

    @classmethod
    def _user_payload(cls, user: PlatformUser) -> dict[str, Any]:
        return {
            "id": str(user.id),
            "email": user.email,
            "role": PLATFORM_ROLE,
            "totp_enabled": user.totp_enabled,
        }

    @classmethod
    def create_session(
        cls,
        user: PlatformUser,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
        session_id: uuid.UUID | None = None,
        family_id: uuid.UUID | None = None,
        family_expires_at: int | None = None,
    ) -> dict[str, Any]:
        """Mint a token pair and register the session in Redis."""
        sid = session_id or uuid.uuid4()
        fid = family_id or uuid.uuid4()
        now_int = int(datetime.now(UTC).timestamp())
        family_exp = family_expires_at or (now_int + PLATFORM_REFRESH_LIFETIME_SECONDS)

        access, _access_jti, _ = platform_mint_access_token(
            platform_user_id=user.id,
            role=PLATFORM_ROLE,
            session_id=sid,
        )
        refresh, refresh_jti, _ = platform_mint_refresh_token(
            platform_user_id=user.id,
            family_id=fid,
            family_expires_at=family_exp,
            session_id=sid,
        )

        platform_register_session(
            user_id=user.id,
            session_id=sid,
            fid=fid,
            refresh_jti=refresh_jti,
            ip=ip or "",
            user_agent=user_agent or "",
            family_expires_at=family_exp,
        )

        return {
            "session_id": str(sid),
            "access": access,
            "expires_in": PLATFORM_ACCESS_LIFETIME_SECONDS,
            "refresh_token": refresh,
            "user": cls._user_payload(user),
        }

    # -- login ------------------------------------------------------------

    @classmethod
    def login(
        cls,
        *,
        email: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Authenticate a platform operator.

        Returns ``(success, payload, error_code)``. The error code is always
        ``invalid_credentials`` for an unknown email, a wrong password or a
        deactivated account — the caller must not distinguish them.
        """
        clean_email = email.strip().lower()
        user = PlatformUser.objects.filter(email=clean_email).first()

        if user is None:
            check_password(password, DUMMY_PASSWORD_HASH)
            with transaction.atomic():
                write_platform_audit(
                    action="auth.login_failed",
                    actor_id=None,
                    entity_id=None,
                    after={"email_attempted": clean_email, "reason": "unknown_email"},
                    ip=ip,
                    user_agent=user_agent,
                )
            return False, None, GENERIC_INVALID_CREDENTIALS

        if not user.check_password(password) or not user.is_active:
            with transaction.atomic():
                write_platform_audit(
                    action="auth.login_failed",
                    actor_id=None,
                    entity_id=user.id,
                    after={
                        "email_attempted": clean_email,
                        "reason": "bad_password",
                    },
                    ip=ip,
                    user_agent=user_agent,
                )
            return False, None, GENERIC_INVALID_CREDENTIALS

        if user.totp_enabled:
            challenge_id = cls.create_totp_challenge(user.id)
            with transaction.atomic():
                write_platform_audit(
                    action="auth.login_succeeded",
                    actor_id=user.id,
                    entity_id=user.id,
                    after={"stage": "password_ok_totp_required"},
                    ip=ip,
                    user_agent=user_agent,
                )
            return True, {"totp_required": True, "challenge_id": challenge_id}, None

        with transaction.atomic():
            payload = cls.create_session(user, ip=ip, user_agent=user_agent)
            write_platform_audit(
                action="auth.login_succeeded",
                actor_id=user.id,
                entity_id=user.id,
                after={"stage": "session_issued", "session_id": payload["session_id"]},
                ip=ip,
                user_agent=user_agent,
            )
        return True, payload, None

    # -- TOTP challenge ---------------------------------------------------

    @classmethod
    def create_totp_challenge(cls, user_id: uuid.UUID) -> str:
        """Store a 5-minute challenge with an attempt counter in Redis."""
        challenge_id = str(uuid.uuid4())
        try:
            cache.set(
                f"platform:auth:challenge:{challenge_id}",
                {"user_id": str(user_id), "attempts": 0},
                timeout=CHALLENGE_TTL_SECONDS,
            )
        except Exception as exc:
            raise PlatformAuthUnavailable(
                f"Platform TOTP challenge store unavailable: {exc}"
            ) from exc
        return challenge_id

    @classmethod
    def verify_totp_challenge(
        cls,
        *,
        email: str,
        challenge_id: str,
        code: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Verify a TOTP (or backup) code against a live challenge."""
        key = f"platform:auth:challenge:{challenge_id}"
        try:
            challenge = cache.get(key)
        except Exception as exc:
            raise PlatformAuthUnavailable(
                f"Platform TOTP challenge store unavailable: {exc}"
            ) from exc
        if not isinstance(challenge, dict):
            return False, None, "totp_challenge_expired"

        attempts = int(challenge.get("attempts", 0)) + 1
        if attempts > CHALLENGE_MAX_ATTEMPTS:
            cache.delete(key)
            return False, None, "totp_challenge_expired"

        user_id = str(challenge.get("user_id", ""))
        user = PlatformUser.objects.filter(id=user_id, is_active=True).first()
        if user is None or user.email.lower() != email.strip().lower():
            cache.delete(key)
            return False, None, "invalid_credentials"

        matched, consumed_hash = cls._match_code(user, code)
        if not matched:
            if attempts >= CHALLENGE_MAX_ATTEMPTS:
                cache.delete(key)
                return False, None, "totp_challenge_expired"
            challenge["attempts"] = attempts
            cache.set(key, challenge, timeout=CHALLENGE_TTL_SECONDS)
            return False, None, "invalid_credentials"

        if consumed_hash is not None:
            with transaction.atomic():
                remaining = [
                    h for h in (user.totp_backup_codes_hash or []) if h != consumed_hash
                ]
                user.totp_backup_codes_hash = remaining
                user.save(update_fields=["totp_backup_codes_hash", "updated_at"])

        cache.delete(key)
        with transaction.atomic():
            payload = cls.create_session(user, ip=ip, user_agent=user_agent)
            write_platform_audit(
                action="auth.login_succeeded",
                actor_id=user.id,
                entity_id=user.id,
                after={
                    "stage": "totp_verified",
                    "session_id": payload["session_id"],
                    "used_backup_code": consumed_hash is not None,
                },
                ip=ip,
                user_agent=user_agent,
            )
        return True, payload, None

    @classmethod
    def _match_code(cls, user: PlatformUser, code: str) -> tuple[bool, str | None]:
        """Return (matched, consumed_backup_hash) for a submitted code."""
        if user.totp_secret_encrypted:
            try:
                raw_secret = cls._fernet().decrypt(user.totp_secret_encrypted.encode())
                # Current window ± one 30s step (clock drift tolerance).
                if pyotp.TOTP(raw_secret.decode()).verify(code, valid_window=1):
                    return True, None
            except Exception as exc:
                logger.error("Platform TOTP secret could not be decrypted: %s", exc)

        for hashed in user.totp_backup_codes_hash or []:
            if check_password(code, hashed):
                return True, hashed
        return False, None

    # -- TOTP enrolment ---------------------------------------------------

    @classmethod
    def enroll_totp(cls, user: PlatformUser) -> tuple[str, str]:
        """Generate a pending secret and its otpauth URI (never persisted raw)."""
        secret = pyotp.random_base32()
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name="LabFlow Platform"
        )
        try:
            cache.set(
                f"platform:auth:totp_pending:{user.id}",
                secret,
                timeout=ENROLLMENT_TTL_SECONDS,
            )
        except Exception as exc:
            raise PlatformAuthUnavailable(
                f"Platform TOTP enrolment store unavailable: {exc}"
            ) from exc
        return secret, uri

    @classmethod
    def confirm_totp_enrollment(
        cls,
        *,
        user: PlatformUser,
        code: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, list[str] | None, str | None]:
        """Activate TOTP and return the raw backup codes exactly once."""
        try:
            pending = cache.get(f"platform:auth:totp_pending:{user.id}")
        except Exception as exc:
            raise PlatformAuthUnavailable(
                f"Platform TOTP enrolment store unavailable: {exc}"
            ) from exc
        if not pending:
            return False, None, "enrolment_expired"

        if not pyotp.TOTP(str(pending)).verify(code, valid_window=1):
            return False, None, "invalid_code"

        encrypted = cls._fernet().encrypt(str(pending).encode()).decode()
        raw_codes = [secrets.token_hex(4).upper() for _ in range(BACKUP_CODE_COUNT)]
        hashed_codes = [make_password(c) for c in raw_codes]

        with transaction.atomic():
            user.totp_secret_encrypted = encrypted
            user.totp_backup_codes_hash = hashed_codes
            user.totp_enabled = True
            user.save(
                update_fields=[
                    "totp_secret_encrypted",
                    "totp_backup_codes_hash",
                    "totp_enabled",
                    "updated_at",
                ]
            )
            write_platform_audit(
                action="auth.totp_enrolled",
                actor_id=user.id,
                entity_id=user.id,
                after={
                    "totp_enabled": True,
                    "backup_codes_issued": BACKUP_CODE_COUNT,
                },
                ip=ip,
                user_agent=user_agent,
            )

        cache.delete(f"platform:auth:totp_pending:{user.id}")
        return True, raw_codes, None

    # -- refresh ----------------------------------------------------------

    @classmethod
    def refresh_tokens(
        cls,
        *,
        raw_refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Rotate a refresh token, detecting reuse (Doc 08 §4.3 SE-05)."""
        if not raw_refresh_token:
            return False, None, "invalid_refresh_token"

        try:
            payload = platform_decode_jwt(raw_refresh_token, expected_type="refresh")
        except ValueError:
            return False, None, "invalid_refresh_token"

        try:
            user_id = uuid.UUID(str(payload["sub"]))
            family_id = uuid.UUID(str(payload["fid"]))
        except (KeyError, ValueError):
            return False, None, "invalid_refresh_token"

        presented_jti = str(payload["jti"])
        family_exp = int(payload["exp"])

        if platform_is_jti_used(presented_jti) or platform_is_jti_denylisted(
            presented_jti
        ):
            capture_security_alert(
                "platform refresh token reuse detected",
                platform_user_id=str(user_id),
                family_id=str(family_id),
            )
            cls.revoke_all_sessions(
                platform_user_id=user_id,
                reason="refresh_reuse",
                ip=ip,
                user_agent=user_agent,
            )
            return False, None, "refresh_reuse_detected"

        marker = platform_get_revocation_marker(user_id)
        if marker is not None and int(payload.get("iat", 0)) < marker:
            return False, None, "invalid_refresh_token"

        sid = payload.get("sid")
        if sid and platform_is_session_revoked(sid):
            return False, None, "invalid_refresh_token"

        now_int = int(time.time())
        if now_int >= family_exp:
            return False, None, "refresh_expired"

        matching = None
        for session in platform_get_active_sessions(user_id):
            if (
                session.get("fid") == str(family_id)
                or session.get("current_refresh_jti") == presented_jti
            ):
                matching = session
                break
        if matching is None:
            return False, None, "invalid_refresh_token"

        user = PlatformUser.objects.filter(id=user_id, is_active=True).first()
        if user is None:
            return False, None, "invalid_credentials"

        platform_mark_jti_used(presented_jti, ttl_seconds=max(1, family_exp - now_int))

        session_id = uuid.UUID(str(matching["id"]))
        with transaction.atomic():
            new_payload = cls.create_session(
                user,
                ip=ip,
                user_agent=user_agent,
                session_id=session_id,
                family_id=family_id,
                family_expires_at=family_exp,
            )
            new_jti = platform_decode_jwt(
                new_payload["refresh_token"], expected_type="refresh"
            )["jti"]
            platform_update_session_refresh_jti(
                user_id=user.id,
                session_id=session_id,
                new_refresh_jti=str(new_jti),
            )
            write_platform_audit(
                action="auth.session_refreshed",
                actor_id=user.id,
                entity_id=user.id,
                after={"session_id": str(session_id), "family_id": str(family_id)},
                ip=ip,
                user_agent=user_agent,
            )

        return (
            True,
            {
                "access": new_payload["access"],
                "expires_in": new_payload["expires_in"],
                "refresh_token": new_payload["refresh_token"],
                # Included so a boot-time silent restore can rebuild the
                # operator identity without a second round trip.
                "user": new_payload["user"],
            },
            None,
        )

    # -- logout / revoke --------------------------------------------------

    @classmethod
    def logout(
        cls,
        *,
        access_token: str | None,
        refresh_token: str | None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> uuid.UUID | None:
        """Denylist the presented tokens and drop the session (SE-07)."""
        now_int = int(time.time())
        sid: str | None = None
        user_id: uuid.UUID | None = None

        if refresh_token:
            try:
                ref = platform_decode_jwt(refresh_token, expected_type="refresh")
                platform_denylist_jti(
                    str(ref["jti"]), ttl_seconds=max(1, int(ref["exp"]) - now_int)
                )
                sid = sid or (str(ref["sid"]) if ref.get("sid") else None)
                user_id = user_id or uuid.UUID(str(ref["sub"]))
            except Exception as exc:
                logger.warning("Platform logout: refresh token rejected: %s", exc)

        if access_token:
            try:
                acc = platform_decode_jwt(access_token, expected_type="access")
                platform_denylist_access_jti(
                    str(acc["jti"]), ttl_seconds=max(1, int(acc["exp"]) - now_int)
                )
                sid = sid or (str(acc["sid"]) if acc.get("sid") else None)
                user_id = user_id or uuid.UUID(str(acc["sub"]))
            except Exception as exc:
                logger.warning("Platform logout: access token rejected: %s", exc)

        if sid and user_id:
            platform_delete_session(user_id, sid)
            platform_mark_session_revoked(sid)

        with transaction.atomic():
            write_platform_audit(
                action="auth.logout",
                actor_id=user_id,
                entity_id=user_id,
                after={"session_id": sid, "refresh_revoked": bool(refresh_token)},
                ip=ip,
                user_agent=user_agent,
            )
        return user_id

    @classmethod
    def revoke_all_sessions(
        cls,
        *,
        platform_user_id: uuid.UUID,
        reason: str,
        ip: str | None = None,
        user_agent: str | None = None,
        except_session_id: uuid.UUID | str | None = None,
        write_audit: bool = True,
    ) -> None:
        """Revoke every session of a platform user.

        ``write_audit=False`` is used by flows that must emit their own single
        audit row (password reset), keeping "one write → one audit row" true.
        """
        if not except_session_id:
            platform_set_revocation_marker(platform_user_id)
        platform_clear_all_sessions(
            platform_user_id, except_session_id=except_session_id
        )
        if not write_audit:
            return
        with transaction.atomic():
            write_platform_audit(
                action="auth.sessions_revoked",
                actor_id=platform_user_id,
                entity_id=platform_user_id,
                after={
                    "reason": reason,
                    "except_session_id": (
                        str(except_session_id) if except_session_id else None
                    ),
                },
                ip=ip,
                user_agent=user_agent,
            )

    # -- password reset ---------------------------------------------------

    @classmethod
    def request_password_reset(
        cls,
        *,
        email: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> str | None:
        """Issue a 60-minute reset token; return the raw token for delivery.

        Returns ``None`` when the account does not exist or the request is
        throttled — the caller answers ``202`` either way.
        """
        clean_email = email.strip().lower()
        if not clean_email or check_and_record_platform_reset_throttle(
            clean_email, ip or ""
        ):
            with transaction.atomic():
                write_platform_audit(
                    action="auth.password_reset_requested",
                    actor_id=None,
                    entity_id=None,
                    after={"email_attempted": clean_email, "dispatched": False},
                    ip=ip,
                    user_agent=user_agent,
                )
            return None

        user = PlatformUser.objects.filter(email=clean_email, is_active=True).first()
        if user is None:
            with transaction.atomic():
                write_platform_audit(
                    action="auth.password_reset_requested",
                    actor_id=None,
                    entity_id=None,
                    after={"email_attempted": clean_email, "dispatched": False},
                    ip=ip,
                    user_agent=user_agent,
                )
            return None

        now = timezone.now()
        raw_token = secrets.token_urlsafe(32)
        with transaction.atomic():
            PlatformPasswordResetToken.objects.filter(
                platform_user=user, used_at__isnull=True
            ).update(used_at=now)
            PlatformPasswordResetToken.objects.create(
                platform_user=user,
                token_hash=make_password(raw_token),
                expires_at=now + timedelta(seconds=PASSWORD_RESET_TTL_SECONDS),
            )
            write_platform_audit(
                action="auth.password_reset_requested",
                actor_id=user.id,
                entity_id=user.id,
                after={"dispatched": True},
                ip=ip,
                user_agent=user_agent,
            )
        return raw_token

    @classmethod
    def confirm_password_reset(
        cls,
        *,
        token: str,
        new_password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """Consume a reset token and rotate the password.

        Returns ``(ok, error_code, error_message)``.
        """
        if not token:
            return False, "invalid_reset_token", "Invalid or expired reset token"

        now = timezone.now()
        candidate = None
        for row in PlatformPasswordResetToken.objects.filter(
            used_at__isnull=True, expires_at__gt=now
        ).select_related("platform_user"):
            if check_password(token, row.token_hash):
                candidate = row
                break
        if candidate is None:
            return False, "invalid_reset_token", "Invalid or expired reset token"

        user = candidate.platform_user
        ok, code, message = validate_platform_password(new_password, user.email)
        if not ok:
            return False, code, message

        with transaction.atomic():
            locked = (
                PlatformPasswordResetToken.objects.select_for_update()
                .filter(id=candidate.id, used_at__isnull=True)
                .first()
            )
            if locked is None or locked.expires_at <= timezone.now():
                return False, "invalid_reset_token", "Invalid or expired reset token"
            locked.used_at = timezone.now()
            locked.save(update_fields=["used_at"])

            user.password_hash = make_password(new_password)
            user.save(update_fields=["password_hash", "updated_at"])

            write_platform_audit(
                action="auth.password_reset",
                actor_id=user.id,
                entity_id=user.id,
                after={"sessions_revoked": True},
                ip=ip,
                user_agent=user_agent,
            )

        cls.revoke_all_sessions(
            platform_user_id=user.id,
            reason="password_reset",
            ip=ip,
            user_agent=user_agent,
            write_audit=False,
        )
        return True, None, None


def is_access_token_revoked(jti: str, sid: str | None) -> bool:
    """True when an access jti or its session was revoked."""
    if platform_is_access_jti_denylisted(jti):
        return True
    return bool(sid and platform_is_session_revoked(sid))


def token_is_stale_for_user(user_id: uuid.UUID, issued_at: int) -> bool:
    """True when a token predates the user's revocation marker."""
    marker = platform_get_revocation_marker(user_id)
    return marker is not None and issued_at < marker
