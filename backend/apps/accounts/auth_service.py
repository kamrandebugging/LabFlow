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
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Final

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django_tenants.utils import schema_context

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
