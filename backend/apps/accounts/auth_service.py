"""High-level AuthService isolating business logic (Doc 08 §4.1, §4.3, §4.6).

Pure business logic:
- Argon2id password verification + dummy hash timing side-channel protection
- Refresh rotation-on-use + reuse detection (SE-05)
- Instant logout via paired access jti denylist (SE-07)
- Reusable revoke_all_sessions service
- Scoped session delete (404 on cross-user attempt)
- LoginEvent & AuditLog emission within same transaction
"""

import logging
import secrets
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Final

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django_tenants.utils import schema_context
import pyotp

from apps.accounts.jwt_engine import (
    ACCESS_TOKEN_LIFETIME_SECONDS,
    REFRESH_TOKEN_LIFETIME_SECONDS,
    decode_jwt,
    mint_access_token,
    mint_refresh_token,
)
from apps.accounts.models import AuditLog, LoginEvent, Role, StaffUser
from apps.accounts.session_registry import (
    clear_all_user_sessions,
    delete_session,
    denylist_access_jti,
    denylist_jti,
    get_active_sessions,
    get_user_revocation_marker,
    is_jti_denylisted,
    is_jti_used,
    is_session_revoked,
    mark_jti_used,
    mark_session_revoked,
    register_session,
    set_user_revocation_marker,
    update_session_refresh_jti,
)

logger = logging.getLogger(__name__)

# Precomputed dummy hash for constant-time failure path when email does not exist
DUMMY_PASSWORD_HASH: Final[str] = make_password("dummy-constant-time-protection-string")

MANDATORY_TOTP_ROLES: Final[set[str]] = {
    Role.OWNER,
    Role.MANAGER,
    Role.PATHOLOGIST,
}


class AuthService:
    """Authentication, token rotation, and session management service."""

    @classmethod
    def login(
        cls,
        email: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Authenticate staff user and return session data or TOTP challenge.

        Returns (success: bool, payload: dict | None, error_code: str | None).
        """
        clean_email = email.strip().lower()
        user = StaffUser.objects.filter(email=clean_email).first()

        if user is None:
            # Constant-time protection: execute hash check on dummy hash
            check_password(password, DUMMY_PASSWORD_HASH)
            LoginEvent.objects.create(
                staff_user=None,
                email_attempted=clean_email,
                success=False,
                ip=ip,
                user_agent=user_agent,
            )
            return False, None, "invalid_credentials"

        # Verify password and active status
        is_correct = check_password(password, user.password_hash)
        if not is_correct or not user.is_active:
            LoginEvent.objects.create(
                staff_user=user,
                email_attempted=clean_email,
                success=False,
                ip=ip,
                user_agent=user_agent,
            )
            return False, None, "invalid_credentials"

        # Check TOTP requirements (Doc 01 §14, Doc 08 §4.1)
        totp_required = user.totp_enabled or (user.role in MANDATORY_TOTP_ROLES)
        if totp_required:
            LoginEvent.objects.create(
                staff_user=user,
                email_attempted=clean_email,
                success=True,
                ip=ip,
                user_agent=user_agent,
            )
            return True, {"totp_required": True, "user_id": str(user.id)}, None

        # Issue full session
        session_data = cls.create_session(
            user,
            ip=ip,
            user_agent=user_agent,
            tenant_id=tenant_id,
        )
        LoginEvent.objects.create(
            staff_user=user,
            email_attempted=clean_email,
            success=True,
            ip=ip,
            user_agent=user_agent,
        )
        return True, session_data, None

    @classmethod
    def create_session(
        cls,
        user: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new session, mint JWTs, and register in Redis."""
        session_id = uuid.uuid4()
        family_id = uuid.uuid4()
        now_int = int(datetime.now(UTC).timestamp())
        family_expires_at = now_int + REFRESH_TOKEN_LIFETIME_SECONDS

        from django.db import connection

        tenant_slug = (
            tenant_id or getattr(connection, "schema_name", "tenant") or "tenant"
        )

        access_token, access_jti, _ = mint_access_token(
            staff_user_id=user.id,
            tenant_slug=tenant_slug,
            role=user.role,
            session_id=session_id,
        )

        refresh_token, refresh_jti, _ = mint_refresh_token(
            staff_user_id=user.id,
            tenant_slug=tenant_slug,
            family_id=family_id,
            family_expires_at=family_expires_at,
            session_id=session_id,
        )

        with schema_context(tenant_slug):
            branch_ids = [str(sb.branch_id) for sb in user.staff_branches.all()]
        if user.branch_id and str(user.branch_id) not in branch_ids:
            branch_ids.append(str(user.branch_id))

        register_session(
            tenant_id=tenant_slug,
            user_id=user.id,
            session_id=session_id,
            fid=family_id,
            refresh_jti=refresh_jti,
            ip=ip or "",
            user_agent=user_agent or "",
            family_expires_at=family_expires_at,
        )

        return {
            "session_id": str(session_id),
            "access": access_token,
            "expires_in": ACCESS_TOKEN_LIFETIME_SECONDS,
            "refresh_token": refresh_token,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "branch_ids": branch_ids,
            },
        }

    @classmethod
    def refresh_tokens(
        cls,
        raw_refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Rotate refresh token or detect token reuse theft (Doc 08 §4.3, SE-05)."""
        if not raw_refresh_token:
            return False, None, "invalid_refresh_token"

        try:
            payload = decode_jwt(raw_refresh_token, expected_type="refresh")
        except ValueError:
            return False, None, "invalid_refresh_token"

        user_id_str = payload["sub"]
        user_id = uuid.UUID(user_id_str)
        presented_jti = payload["jti"]
        family_id = uuid.UUID(payload["fid"])
        family_exp = payload["exp"]
        tenant_slug = payload.get("tenant", "tenant")

        # Reuse Detection: jti already marked used or denylisted (SE-05)
        if is_jti_used(presented_jti) or is_jti_denylisted(presented_jti):
            logger.warning(
                "se_05_refresh_reuse_detected: user %s, family %s",
                user_id,
                family_id,
            )
            cls.revoke_all_sessions(
                staff_user_id=user_id,
                tenant_id=tenant_slug,
                reason="refresh_reuse",
                ip=ip,
                user_agent=user_agent,
            )
            return False, None, "refresh_reuse_detected"

        # Revocation marker check
        revocation_marker = get_user_revocation_marker(user_id)
        if revocation_marker and payload["iat"] < revocation_marker:
            return False, None, "invalid_refresh_token"

        # Check per-session revocation marker
        sid = payload.get("sid")
        if sid and is_session_revoked(sid):
            return False, None, "invalid_refresh_token"

        # Check family lifetime cap
        now_int = int(time.time())
        if now_int >= family_exp:
            return False, None, "refresh_expired"

        # Find matching session
        active_sessions = get_active_sessions(tenant_slug, user_id)
        matching_session = None
        for s in active_sessions:
            if (
                s.get("fid") == str(family_id)
                or s.get("current_refresh_jti") == presented_jti
            ):
                matching_session = s
                break

        if not matching_session:
            return False, None, "invalid_refresh_token"

        user = StaffUser.objects.filter(id=user_id, is_active=True).first()
        if not user:
            return False, None, "invalid_credentials"

        # Mark presented jti as used
        remaining_ttl = max(1, family_exp - now_int)
        mark_jti_used(presented_jti, ttl_seconds=remaining_ttl)

        # Mint new tokens in same family
        session_id = matching_session["id"]
        new_access_token, _, _ = mint_access_token(
            staff_user_id=user.id,
            tenant_slug=tenant_slug,
            role=user.role,
            session_id=session_id,
        )
        new_refresh_token, new_refresh_jti, _ = mint_refresh_token(
            staff_user_id=user.id,
            tenant_slug=tenant_slug,
            family_id=family_id,
            family_expires_at=family_exp,
            session_id=session_id,
        )

        update_session_refresh_jti(
            tenant_id=tenant_slug,
            user_id=user.id,
            session_id=matching_session["id"],
            new_refresh_jti=new_refresh_jti,
        )

        return (
            True,
            {
                "access": new_access_token,
                "expires_in": ACCESS_TOKEN_LIFETIME_SECONDS,
                "refresh_token": new_refresh_token,
            },
            None,
        )

    @classmethod
    def logout(
        cls,
        access_token: str | None,
        refresh_token: str | None,
        staff_user_id: uuid.UUID | None = None,
        tenant_id: str = "tenant",
    ) -> None:
        """Denylist tokens and remove session registry (Doc 08 §4.3, SE-07)."""
        sid = None
        if refresh_token:
            try:
                ref_payload = decode_jwt(refresh_token, expected_type="refresh")
                ref_jti = ref_payload["jti"]
                ttl = max(1, ref_payload["exp"] - int(time.time()))
                denylist_jti(ref_jti, ttl_seconds=ttl)
                sid = sid or ref_payload.get("sid")
            except Exception as exc:
                logger.warning("Logout error decoding refresh token: %s", exc)

        if access_token:
            try:
                acc_payload = decode_jwt(access_token, expected_type="access")
                acc_jti = acc_payload["jti"]
                ttl = max(1, acc_payload["exp"] - int(time.time()))
                denylist_access_jti(acc_jti, ttl_seconds=ttl)
                sid = sid or acc_payload.get("sid")
            except Exception as exc:
                logger.warning("Logout error decoding access token: %s", exc)

        if sid and staff_user_id:
            delete_session(tenant_id, staff_user_id, sid)
            mark_session_revoked(sid)

    @classmethod
    def list_active_sessions(
        cls,
        staff_user_id: uuid.UUID,
        current_session_id: uuid.UUID | str | None = None,
        tenant_id: str = "tenant",
    ) -> list[dict[str, Any]]:
        """List caller's active sessions with current marker and zero secrets."""
        raw_sessions = get_active_sessions(tenant_id, staff_user_id)
        cur_sid = str(current_session_id) if current_session_id else None

        result: list[dict[str, Any]] = []
        for s in raw_sessions:
            result.append(
                {
                    "id": s["id"],
                    "ip": s.get("ip", ""),
                    "user_agent": s.get("user_agent", ""),
                    "created_at": s.get("created_at"),
                    "last_active": s.get("last_active"),
                    "current": bool(cur_sid and s["id"] == cur_sid),
                }
            )
        return result

    @classmethod
    def revoke_remote_session(
        cls,
        caller_user_id: uuid.UUID,
        session_id: uuid.UUID | str,
        tenant_id: str = "tenant",
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Scoped delete: WHERE user_id=:caller AND id=:sessionId (Doc 08 §4.6)."""
        deleted_session = delete_session(tenant_id, caller_user_id, session_id)
        if not deleted_session:
            return False

        # Denylist current refresh jti
        if "current_refresh_jti" in deleted_session:
            denylist_jti(deleted_session["current_refresh_jti"])

        # Write audit log row within tenant schema
        with schema_context(tenant_id), transaction.atomic():
            AuditLog.objects.create(
                actor_id=caller_user_id,
                action="auth.session_revoked",
                entity_type="session",
                entity_id=uuid.UUID(str(session_id)),
                before_jsonb={"session_id": str(session_id)},
                after_jsonb={"status": "revoked"},
                ip=ip,
                user_agent=user_agent,
            )
        return True

    @classmethod
    def revoke_all_sessions(
        cls,
        staff_user_id: uuid.UUID,
        tenant_id: str = "tenant",
        except_session_id: uuid.UUID | str | None = None,
        reason: str = "user_revoke",
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Reusable revoke-all method (theft detection, password change)."""
        if not except_session_id:
            set_user_revocation_marker(staff_user_id)
        clear_all_user_sessions(
            tenant_id, staff_user_id, except_session_id=except_session_id
        )

        try:
            with schema_context(tenant_id), transaction.atomic():
                AuditLog.objects.create(
                    actor_id=staff_user_id,
                    action="auth.sessions_revoked",
                    entity_type="staff_user",
                    entity_id=staff_user_id,
                    after_jsonb={
                        "reason": reason,
                        "except_session_id": str(except_session_id)
                        if except_session_id
                        else None,
                    },
                    ip=ip,
                    user_agent=user_agent,
                )
        except Exception as exc:
            logger.warning("AuditLog creation in revoke_all_sessions failed: %s", exc)

    @classmethod
    def change_password(
        cls,
        staff_user: StaffUser,
        current_password: str,
        new_password: str,
        current_session_id: uuid.UUID | str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        tenant_id: str = "tenant",
    ) -> tuple[bool, str | None]:
        """Update password hash and revoke all other sessions."""
        if not check_password(current_password, staff_user.password_hash):
            return False, "invalid_credentials"

        with transaction.atomic():
            staff_user.password_hash = make_password(new_password)
            staff_user.save(update_fields=["password_hash", "updated_at"])

            AuditLog.objects.create(
                actor_id=staff_user.id,
                action="auth.password_changed",
                entity_type="staff_user",
                entity_id=staff_user.id,
                after_jsonb={"status": "password_updated"},
                ip=ip,
                user_agent=user_agent,
            )

        # Revoke all other sessions (current session stays active)
        cls.revoke_all_sessions(
            staff_user_id=staff_user.id,
            tenant_id=tenant_id,
            except_session_id=current_session_id,
            reason="password_change",
            ip=ip,
            user_agent=user_agent,
        )
        return True, None

    # --------------------------------------------------------------------------
    # LAB-12: MFA TOTP Enrolment, Verification & Reset (Doc 08 §4.4)
    # --------------------------------------------------------------------------

    @classmethod
    def _get_fernet(cls) -> Fernet:
        key = getattr(settings, "LABFLOW_TOTP_ENCRYPTION_KEY", None)
        if not key:
            raise RuntimeError("LABFLOW_TOTP_ENCRYPTION_KEY is not configured")
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    @classmethod
    def create_totp_challenge(cls, user_id: str) -> str:
        """Create a 5-minute TOTP challenge in Redis tracking attempts (Doc 08 §4.4)."""
        challenge_token = str(uuid.uuid4())
        cache_key = f"auth:challenge:{challenge_token}"
        cache.set(cache_key, {"user_id": user_id, "attempts": 0}, timeout=300)
        return challenge_token

    @classmethod
    def enroll_totp(cls, user: StaffUser) -> tuple[str, str]:
        """Generate pending secret and otpauth URI (Doc 08 §4.4, §17 A-25)."""
        secret = pyotp.random_base32()
        otpauth_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="LabFlow",
        )
        # Store pending secret in Redis for 15 minutes
        cache.set(f"auth:totp_pending:{user.id}", secret, timeout=900)
        return secret, otpauth_uri

    @classmethod
    def confirm_totp_enrollment(
        cls,
        user: StaffUser,
        code: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, list[str] | None, str | None]:
        """Confirm pending TOTP secret with code and issue 10 backup codes."""
        pending_secret = cache.get(f"auth:totp_pending:{user.id}")
        if not pending_secret:
            return False, None, "enrolment_expired"

        totp = pyotp.TOTP(pending_secret)
        if not totp.verify(code, valid_window=1):
            return False, None, "invalid_code"

        fernet = cls._get_fernet()
        encrypted_secret = fernet.encrypt(pending_secret.encode()).decode()

        # Generate 10 single-use alphanumeric backup codes (Doc 08 §4.4)
        raw_codes = [secrets.token_hex(4).upper() for _ in range(10)]
        hashed_codes = [make_password(c) for c in raw_codes]

        with transaction.atomic():
            user.totp_secret_encrypted = encrypted_secret
            user.totp_backup_codes_hash = hashed_codes
            user.totp_enabled = True
            user.save(update_fields=["totp_secret_encrypted", "totp_backup_codes_hash", "totp_enabled", "updated_at"])

            AuditLog.objects.create(
                actor_id=user.id,
                action="auth.totp_enrolled",
                entity_type="staff_user",
                entity_id=user.id,
                after_jsonb={"totp_enabled": True},
                ip=ip,
                user_agent=user_agent,
            )

        cache.delete(f"auth:totp_pending:{user.id}")
        return True, raw_codes, None

    @classmethod
    def verify_totp_challenge(
        cls,
        challenge_token: str,
        code: str,
        ip: str | None = None,
        user_agent: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Verify code against 5-min challenge with ±1 window drift & backup fallback."""
        cache_key = f"auth:challenge:{challenge_token}"
        challenge = cache.get(cache_key)
        if not challenge:
            return False, None, "totp_challenge_expired"

        attempts = challenge.get("attempts", 0) + 1
        challenge["attempts"] = attempts

        if attempts > 5:
            cache.delete(cache_key)
            return False, None, "totp_challenge_expired"

        user_id = challenge.get("user_id")
        user = StaffUser.objects.filter(id=user_id, is_active=True).first()
        if not user:
            cache.delete(cache_key)
            return False, None, "invalid_credentials"

        is_matched = False

        # 1. Try TOTP secret match if enrolled
        if user.totp_secret_encrypted:
            try:
                fernet = cls._get_fernet()
                raw_secret = fernet.decrypt(user.totp_secret_encrypted.encode()).decode()
                totp = pyotp.TOTP(raw_secret)
                if totp.verify(code, valid_window=1):
                    is_matched = True
            except Exception as exc:
                logger.error("Failed decrypting TOTP secret: %s", exc)

        # 2. Try single-use backup code match if not matched by TOTP
        if not is_matched and user.totp_backup_codes_hash:
            matched_hash = None
            for h in user.totp_backup_codes_hash:
                if check_password(code, h):
                    matched_hash = h
                    is_matched = True
                    break

            if matched_hash:
                with transaction.atomic():
                    user.totp_backup_codes_hash.remove(matched_hash)
                    user.save(update_fields=["totp_backup_codes_hash", "updated_at"])

        if not is_matched:
            if attempts >= 5:
                cache.delete(cache_key)
                return False, None, "totp_challenge_expired"
            cache.set(cache_key, challenge, timeout=300)
            return False, None, "invalid_credentials"

        # Verification succeeded
        cache.delete(cache_key)
        session_data = cls.create_session(
            user,
            ip=ip,
            user_agent=user_agent,
            tenant_id=tenant_id,
        )
        LoginEvent.objects.create(
            staff_user=user,
            email_attempted=user.email,
            success=True,
            ip=ip,
            user_agent=user_agent,
        )
        return True, session_data, None

    @classmethod
    def reset_staff_totp(
        cls,
        actor: StaffUser,
        target_user: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bool, str | None]:
        """Owner resets staff TOTP (Doc 08 §4.4, LAB-52)."""
        if actor.role != Role.OWNER:
            return False, "forbidden"

        with transaction.atomic():
            target_user.totp_secret_encrypted = None
            target_user.totp_backup_codes_hash = None
            target_user.totp_enabled = False
            target_user.save(update_fields=["totp_secret_encrypted", "totp_backup_codes_hash", "totp_enabled", "updated_at"])

            AuditLog.objects.create(
                actor_id=actor.id,
                action="auth.totp_reset",
                entity_type="staff_user",
                entity_id=target_user.id,
                after_jsonb={"totp_enabled": False, "reset_by": str(actor.id)},
                ip=ip,
                user_agent=user_agent,
            )
        return True, None

