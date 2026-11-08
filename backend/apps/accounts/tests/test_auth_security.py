"""Automated Security & Verification Test Suite for LabFlow Auth & Sessions.

Governed by:
- Doc 08 §4.1, §4.3, §4.4 (SE-02, SE-03, SE-04, SE-05, SE-07)
- Doc 07 §17 A-25 (MFA TOTP Enrolment & Verification)
- Doc 04 §13 (Multi-tenant schema isolation)

Covers:
1. TOTP challenge created on valid password login for staff with
   totp_enabled=True.
2. Successful TOTP verification with valid 6-digit code returns access
   token, refresh token, and user session within tenant schema_context.
3. Invalid TOTP code rejection (returns 401 invalid_credentials).
4. TOTP challenge max attempts lockout (5 failed attempts deletes
   challenge and locks out further attempts with 401 totp_challenge_expired).
5. Challenge token expired or missing rejection (401 totp_challenge_expired).
6. Refresh token rotation (SE-05): presenting a valid refresh token
   returns new access and refresh tokens, marking old jti used.
7. Refresh token reuse detection (SE-05): presenting an already used
   refresh token triggers theft detection and revokes all sessions in family.
8. Logout (SE-07): denylists tokens and clears active session in Redis.
9. Schema isolation check: verifying TOTP challenge loads user from tenant
   schema, NOT failing with relation does not exist.
10. Single-use backup code verification and atomic consumption.
"""

import uuid
from typing import Any

import pyotp
import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import Client
from django_tenants.utils import schema_context

from apps.accounts.auth_service import AuthService
from apps.accounts.jwt_engine import decode_jwt
from apps.accounts.models import AuditLog, LoginEvent, Role, StaffUser
from apps.accounts.session_registry import (
    get_active_sessions,
    get_user_revocation_marker,
    is_access_jti_denylisted,
    is_jti_denylisted,
    is_jti_used,
)


@pytest.fixture(autouse=True)
def clear_cache() -> Any:
    """Ensure clean cache/Redis state before and after each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client_tenant_a(tenant_a: Any) -> Client:
    """HTTP client bound to tenant_a host."""
    return Client(HTTP_HOST="tenant-a.localhost")


@pytest.fixture
def client_tenant_b(tenant_b: Any) -> Client:
    """HTTP client bound to tenant_b host."""
    return Client(HTTP_HOST="tenant-b.localhost")


@pytest.fixture
def regular_staff(tenant_a: Any) -> StaffUser:
    """Staff user without TOTP enabled (receptionist)."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="receptionist@labflow.local",
            password_hash=make_password("ReceptionPassword123!"),
            role=Role.RECEPTION,
            is_active=True,
            totp_enabled=False,
        )


@pytest.fixture
def totp_staff(tenant_a: Any) -> tuple[StaffUser, str]:
    """Staff user with TOTP enabled and Fernet-encrypted secret in tenant_a."""
    raw_secret = pyotp.random_base32()
    fernet = Fernet(settings.LABFLOW_TOTP_ENCRYPTION_KEY.encode())
    encrypted_secret = fernet.encrypt(raw_secret.encode()).decode()

    with schema_context(tenant_a.schema_name):
        user = StaffUser.objects.create(
            email="tech_totp@labflow.local",
            password_hash=make_password("TechSecurePassword123!"),
            role=Role.TECHNICIAN,
            is_active=True,
            totp_enabled=True,
            totp_secret_encrypted=encrypted_secret,
            totp_backup_codes_hash=[
                make_password("BACKUP-01"),
                make_password("BACKUP-02"),
            ],
        )
        return user, raw_secret


@pytest.mark.django_db
@pytest.mark.tenancy
class TestAuthSecurityAndSessionVerification:
    """Comprehensive test suite for LabFlow Authentication and Session Verification."""

    def test_totp_challenge_created_on_valid_password_login_for_totp_staff(
        self,
        client_tenant_a: Client,
        totp_staff: tuple[StaffUser, str],
        tenant_a: Any,
    ) -> None:
        """Requirement 1: TOTP challenge created for totp_enabled=True staff."""
        user, _ = totp_staff

        response = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": user.email,
                "password": "TechSecurePassword123!",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()

        # 1. Verification payload
        assert data.get("totp_required") is True
        assert "challenge_token" in data
        assert data.get("email") == user.email.lower()

        # 2. Strict DoD requirements: no access token, no refresh cookie yet
        assert "access" not in data
        assert "refresh_token" not in response.cookies

        # 3. Challenge cookie set
        assert "auth_challenge" in response.cookies
        challenge_cookie = response.cookies["auth_challenge"]
        assert challenge_cookie["httponly"] is True
        assert challenge_cookie.value == data["challenge_token"]

        # 4. Redis cache state
        challenge_token = data["challenge_token"]
        cached_challenge = cache.get(f"auth:challenge:{challenge_token}")
        assert cached_challenge is not None
        assert cached_challenge["user_id"] == str(user.id)
        assert cached_challenge["attempts"] == 0
        assert cached_challenge["tenant_id"] == tenant_a.schema_name

    def test_totp_verify_success_returns_tokens_and_registers_session(
        self,
        client_tenant_a: Client,
        totp_staff: tuple[StaffUser, str],
        tenant_a: Any,
    ) -> None:
        """Requirement 2: Successful TOTP verification returns tokens and session."""
        user, raw_secret = totp_staff

        # Step 1: Login to initiate TOTP challenge
        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": user.email,
                "password": "TechSecurePassword123!",
            },
            content_type="application/json",
        )
        assert login_res.status_code == 200
        challenge_token = login_res.json()["challenge_token"]

        # Step 2: Generate valid 6-digit TOTP code
        totp = pyotp.TOTP(raw_secret)
        code = totp.now()

        # Step 3: Verify TOTP code
        client_tenant_a.cookies["auth_challenge"] = challenge_token
        verify_res = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": code},
            content_type="application/json",
        )

        assert verify_res.status_code == 200
        data = verify_res.json()

        # Access token and user payload
        assert "access" in data
        assert data.get("expires_in") == 900
        assert data["user"]["id"] == str(user.id)
        assert data["user"]["email"] == user.email
        assert data["user"]["role"] == Role.TECHNICIAN

        # Refresh token stored in httpOnly cookie ONLY (SE-05 DoD)
        assert "refresh" not in data
        assert "refresh_token" not in data
        assert "refresh_token" in verify_res.cookies
        ref_cookie = verify_res.cookies["refresh_token"]
        assert ref_cookie["httponly"] is True
        assert ref_cookie["path"] == "/api/v1/auth/"
        assert ref_cookie["samesite"].lower() == "lax"

        # Challenge cookie cleared
        assert verify_res.cookies["auth_challenge"].value == ""

        # Redis session registered
        sessions = get_active_sessions(tenant_a.schema_name, user.id)
        assert len(sessions) == 1
        assert sessions[0]["ip"] is not None

        # Access token allows calling protected endpoint
        access_token = data["access"]
        session_res = client_tenant_a.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert session_res.status_code == 200

        # Successful LoginEvent logged in tenant schema
        with schema_context(tenant_a.schema_name):
            event = LoginEvent.objects.filter(
                email_attempted=user.email, success=True
            ).first()
            assert event is not None
            assert event.staff_user == user

    def test_totp_verify_invalid_code_rejection(
        self,
        client_tenant_a: Client,
        totp_staff: tuple[StaffUser, str],
    ) -> None:
        """Requirement 3: Invalid code rejected (returns 401 invalid_credentials)."""
        user, _ = totp_staff

        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": user.email,
                "password": "TechSecurePassword123!",
            },
            content_type="application/json",
        )
        challenge_token = login_res.json()["challenge_token"]

        # Attempt verification with wrong code
        client_tenant_a.cookies["auth_challenge"] = challenge_token
        verify_res = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": "000000"},
            content_type="application/json",
        )

        assert verify_res.status_code == 401
        data = verify_res.json()
        assert data["error"]["code"] == "invalid_credentials"
        assert "access" not in data
        assert "refresh_token" not in verify_res.cookies

        # Challenge still exists and attempt count incremented
        challenge_state = cache.get(f"auth:challenge:{challenge_token}")
        assert challenge_state is not None
        assert challenge_state["attempts"] == 1

    def test_totp_challenge_max_attempts_lockout(
        self,
        client_tenant_a: Client,
        totp_staff: tuple[StaffUser, str],
    ) -> None:
        """Requirement 4: 5 failed attempts deletes challenge and locks out."""
        user, raw_secret = totp_staff

        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": user.email,
                "password": "TechSecurePassword123!",
            },
            content_type="application/json",
        )
        challenge_token = login_res.json()["challenge_token"]
        client_tenant_a.cookies["auth_challenge"] = challenge_token

        # Attempts 1 to 4 fail with invalid_credentials
        for _ in range(4):
            res = client_tenant_a.post(
                "/api/v1/auth/totp/verify",
                data={"code": "999999"},
                content_type="application/json",
            )
            assert res.status_code == 401
            assert res.json()["error"]["code"] == "invalid_credentials"

        # 5th attempt locks out and destroys the challenge
        res5 = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": "999999"},
            content_type="application/json",
        )
        assert res5.status_code == 401
        assert res5.json()["error"]["code"] == "totp_challenge_expired"

        # Redis challenge key must be gone
        assert cache.get(f"auth:challenge:{challenge_token}") is None

        # 6th attempt (even with valid TOTP code) is rejected as expired
        totp = pyotp.TOTP(raw_secret)
        res6 = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": totp.now()},
            content_type="application/json",
        )
        assert res6.status_code == 401
        assert res6.json()["error"]["code"] == "totp_challenge_expired"

    def test_totp_challenge_expired_or_missing_rejection(
        self,
        client_tenant_a: Client,
    ) -> None:
        """Requirement 5: Expired/missing challenge returns totp_challenge_expired."""
        # Case A: Missing challenge token entirely
        res_missing = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": "123456"},
            content_type="application/json",
        )
        assert res_missing.status_code == 401
        assert res_missing.json()["error"]["code"] == "totp_challenge_expired"

        # Case B: Expired / nonexistent challenge token passed in payload
        res_expired = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={
                "code": "123456",
                "challenge_token": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        assert res_expired.status_code == 401
        assert res_expired.json()["error"]["code"] == "totp_challenge_expired"

    def test_refresh_token_rotation_updates_jti_and_marks_old_used(
        self,
        client_tenant_a: Client,
        regular_staff: StaffUser,
        tenant_a: Any,
    ) -> None:
        """Requirement 6: Rotation returns new tokens and marks old jti used (SE-05)."""
        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": regular_staff.email,
                "password": "ReceptionPassword123!",
            },
            content_type="application/json",
        )
        assert login_res.status_code == 200
        token_v1 = login_res.cookies["refresh_token"].value
        payload_v1 = decode_jwt(token_v1, expected_type="refresh")
        jti_v1 = payload_v1["jti"]

        assert is_jti_used(jti_v1) is False

        # Present token_v1 to rotate
        client_tenant_a.cookies["refresh_token"] = token_v1
        refresh_res = client_tenant_a.post("/api/v1/auth/refresh")
        assert refresh_res.status_code == 200
        refresh_data = refresh_res.json()

        assert "access" in refresh_data
        assert refresh_data.get("expires_in") == 900
        assert "refresh" not in refresh_data

        token_v2 = refresh_res.cookies["refresh_token"].value
        assert token_v2 != token_v1

        payload_v2 = decode_jwt(token_v2, expected_type="refresh")
        jti_v2 = payload_v2["jti"]

        # SE-05: Old jti is marked used in Redis
        assert is_jti_used(jti_v1) is True
        # New jti is active and not used
        assert is_jti_used(jti_v2) is False

        # Session registry in Redis is updated with jti_v2
        sessions = get_active_sessions(tenant_a.schema_name, regular_staff.id)
        assert len(sessions) == 1
        assert sessions[0]["current_refresh_jti"] == jti_v2

    def test_refresh_token_reuse_detection_revokes_all_sessions(
        self,
        client_tenant_a: Client,
        regular_staff: StaffUser,
        tenant_a: Any,
    ) -> None:
        """Requirement 7: Reuse detection revokes all sessions in family (SE-05)."""
        # Step 1: Initial login
        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": regular_staff.email,
                "password": "ReceptionPassword123!",
            },
            content_type="application/json",
        )
        token_v1 = login_res.cookies["refresh_token"].value

        # Step 2: Legitimate rotation -> receives token_v2
        client_tenant_a.cookies["refresh_token"] = token_v1
        rot_res = client_tenant_a.post("/api/v1/auth/refresh")
        assert rot_res.status_code == 200
        token_v2 = rot_res.cookies["refresh_token"].value

        # Step 3: Attacker replays already rotated token_v1
        client_tenant_a.cookies["refresh_token"] = token_v1
        theft_res = client_tenant_a.post("/api/v1/auth/refresh")

        assert theft_res.status_code == 401
        assert theft_res.json()["error"]["code"] == "refresh_reuse_detected"

        # Step 4: Verification that all sessions for this user were revoked
        sessions = get_active_sessions(tenant_a.schema_name, regular_staff.id)
        assert len(sessions) == 0

        # Step 5: User revocation marker set
        marker = get_user_revocation_marker(regular_staff.id)
        assert marker is not None

        # Step 6: Legitimate client can no longer refresh with token_v2
        client_tenant_a.cookies["refresh_token"] = token_v2
        second_res = client_tenant_a.post("/api/v1/auth/refresh")
        assert second_res.status_code == 401

        # Step 7: AuditLog written in tenant schema recording theft detection
        with schema_context(tenant_a.schema_name):
            audit = AuditLog.objects.filter(
                actor_id=regular_staff.id,
                action="auth.sessions_revoked",
            ).first()
            assert audit is not None
            assert isinstance(audit.after_jsonb, dict)
            assert audit.after_jsonb.get("reason") == "refresh_reuse"

    def test_logout_denylists_tokens_and_clears_session_in_redis(
        self,
        client_tenant_a: Client,
        regular_staff: StaffUser,
        tenant_a: Any,
    ) -> None:
        """Requirement 8: Logout (SE-07): denylists tokens and clears Redis session."""
        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": regular_staff.email,
                "password": "ReceptionPassword123!",
            },
            content_type="application/json",
        )
        access_token = login_res.json()["access"]
        refresh_token = login_res.cookies["refresh_token"].value

        acc_payload = decode_jwt(access_token, expected_type="access")
        ref_payload = decode_jwt(refresh_token, expected_type="refresh")
        acc_jti = acc_payload["jti"]
        ref_jti = ref_payload["jti"]

        # Confirm session exists before logout
        assert len(get_active_sessions(tenant_a.schema_name, regular_staff.id)) == 1

        # Perform logout
        client_tenant_a.cookies["refresh_token"] = refresh_token
        logout_res = client_tenant_a.post(
            "/api/v1/auth/logout",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert logout_res.status_code == 204
        assert logout_res.cookies["refresh_token"]["max-age"] == 0

        # Session purged from Redis
        assert len(get_active_sessions(tenant_a.schema_name, regular_staff.id)) == 0

        # JTI denylists populated
        assert is_access_jti_denylisted(acc_jti) is True
        assert is_jti_denylisted(ref_jti) is True

        # Subsequent use of logged-out access token is rejected immediately (SE-07)
        after_access_res = client_tenant_a.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert after_access_res.status_code == 401

        # Subsequent refresh attempt with logged-out refresh token is rejected
        client_tenant_a.cookies["refresh_token"] = refresh_token
        after_refresh_res = client_tenant_a.post("/api/v1/auth/refresh")
        assert after_refresh_res.status_code == 401

    def test_schema_isolation_totp_challenge_loads_user_from_tenant_schema(
        self,
        client_tenant_a: Client,
        client_tenant_b: Client,
        totp_staff: tuple[StaffUser, str],
        tenant_a: Any,
        tenant_b: Any,
    ) -> None:
        """Requirement 9: Verifying TOTP challenge loads user from tenant schema."""
        user, raw_secret = totp_staff

        # Step 1: Login on tenant-a domain
        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": user.email,
                "password": "TechSecurePassword123!",
            },
            content_type="application/json",
        )
        assert login_res.status_code == 200
        challenge_token = login_res.json()["challenge_token"]

        # Step 2: Direct service verification verifies tenant schema isolation
        success, payload, err = AuthService.verify_totp_challenge(
            challenge_token=challenge_token,
            code=pyotp.TOTP(raw_secret).now(),
            tenant_id=tenant_a.schema_name,
        )
        assert success is True
        assert payload is not None
        assert err is None
        assert payload["user"]["email"] == user.email

        # Step 3: Cross-tenant isolation check:
        # Create fresh challenge in tenant_a
        fresh_challenge = AuthService.create_totp_challenge(
            str(user.id), tenant_id=tenant_a.schema_name
        )

        # Presenting tenant_a challenge to tenant_b domain
        client_tenant_b.cookies["auth_challenge"] = fresh_challenge
        cross_res = client_tenant_b.post(
            "/api/v1/auth/totp/verify",
            data={"code": pyotp.TOTP(raw_secret).now()},
            content_type="application/json",
        )
        # Must fail with 401 invalid_credentials because user is not in tenant_b
        assert cross_res.status_code == 401
        assert cross_res.json()["error"]["code"] == "invalid_credentials"

    def test_totp_verify_with_single_use_backup_code(
        self,
        client_tenant_a: Client,
        totp_staff: tuple[StaffUser, str],
        tenant_a: Any,
    ) -> None:
        """Requirement 10: Backup code verification and atomic consumption."""
        user, _ = totp_staff
        backup_code = "BACKUP-01"

        # Login -> get challenge
        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": user.email,
                "password": "TechSecurePassword123!",
            },
            content_type="application/json",
        )
        challenge_token = login_res.json()["challenge_token"]

        # Verify using single-use backup code
        client_tenant_a.cookies["auth_challenge"] = challenge_token
        verify_res = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": backup_code},
            content_type="application/json",
        )
        assert verify_res.status_code == 200
        assert "access" in verify_res.json()
        assert "refresh_token" in verify_res.cookies

        # Backup code consumed in tenant DB (only 1 remaining)
        with schema_context(tenant_a.schema_name):
            updated_user = StaffUser.objects.get(id=user.id)
            assert updated_user.totp_backup_codes_hash is not None
            assert len(updated_user.totp_backup_codes_hash) == 1

        # Replaying the same backup code fails
        login_res2 = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": user.email,
                "password": "TechSecurePassword123!",
            },
            content_type="application/json",
        )
        challenge2 = login_res2.json()["challenge_token"]
        client_tenant_a.cookies["auth_challenge"] = challenge2

        replay_res = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": backup_code},
            content_type="application/json",
        )
        assert replay_res.status_code == 401
        assert replay_res.json()["error"]["code"] == "invalid_credentials"
