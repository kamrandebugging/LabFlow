"""Tests for LAB-12: MFA Security - TOTP Enrolment, Verify, Backup Codes & Reset.

Governed strictly by Doc 08 §4.4 (SE-02, SE-03, SE-04) and Doc 07 §17 A-25.
"""

from typing import Any
import uuid
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import Client
from django_tenants.utils import schema_context
import pyotp
import pytest

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def receptionist(tenant_a: Any) -> StaffUser:
    """Staff user for voluntary TOTP enrolment."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="receptionist@lab12.com",
            password_hash=make_password("ReceptionPass123!"),
            role=Role.RECEPTION,
            is_active=True,
        )


@pytest.fixture
def owner(tenant_a: Any) -> StaffUser:
    """Owner account with mandatory TOTP."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="owner@lab12.com",
            password_hash=make_password("OwnerPasswordSecure123!"),
            role=Role.OWNER,
            is_active=True,
        )


@pytest.fixture
def client(tenant_a: Any) -> Client:
    return Client(HTTP_HOST="tenant-a.localhost")


def _get_auth_headers(user: StaffUser, tenant_slug: str) -> dict[str, str]:
    with schema_context(tenant_slug):
        session = AuthService.create_session(user, tenant_id=tenant_slug)
    return {"HTTP_AUTHORIZATION": f"Bearer {session['access']}"}


@pytest.mark.tenancy
@pytest.mark.django_db
class TestLAB12TotpEnrolmentAndVerification:
    """SE-02, SE-03, SE-04: Full MFA suite."""

    def test_totp_enrol_generates_secret_and_otpauth_uri(
        self, client: Client, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """Doc 08 §4.4 step 1: POST /api/v1/auth/totp/enroll."""
        headers = _get_auth_headers(receptionist, tenant_a.schema_name)
        response = client.post("/api/v1/auth/totp/enroll", **headers)

        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "otpauth_uri" in data
        assert data["otpauth_uri"].startswith("otpauth://totp/")
        assert "receptionist%40lab12.com" in data["otpauth_uri"] or "receptionist@lab12.com" in data["otpauth_uri"]

    def test_totp_enrol_confirm_activates_totp_and_issues_10_backup_codes(
        self, client: Client, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """Doc 08 §4.4 steps 2-4: Confirm secret, store Fernet-encrypted & return 10 codes."""
        headers = _get_auth_headers(receptionist, tenant_a.schema_name)
        enrol_res = client.post("/api/v1/auth/totp/enroll", **headers)
        secret = enrol_res.json()["secret"]

        # Generate valid TOTP code
        code = pyotp.TOTP(secret).now()

        confirm_res = client.post(
            "/api/v1/auth/totp/enroll/confirm",
            data={"code": code},
            content_type="application/json",
            **headers,
        )

        assert confirm_res.status_code == 200
        data = confirm_res.json()
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10

        # Verify DB state in tenant
        with schema_context(tenant_a.schema_name):
            user = StaffUser.objects.get(id=receptionist.id)
            assert user.totp_enabled is True
            assert user.totp_secret_encrypted is not None
            # Secret must be encrypted with Fernet, not stored as plaintext base32
            assert user.totp_secret_encrypted != secret
            fernet = Fernet(settings.LABFLOW_TOTP_ENCRYPTION_KEY.encode())
            decrypted = fernet.decrypt(user.totp_secret_encrypted.encode()).decode()
            assert decrypted == secret

            # 10 hashed backup codes stored
            assert len(user.totp_backup_codes_hash) == 10

            # Audit log emitted without secret or backup codes
            audit = AuditLog.objects.filter(
                actor_id=user.id,
                action="auth.totp_enrolled",
            ).first()
            assert audit is not None
            assert secret not in str(audit.after_jsonb)

    def test_totp_confirm_rejects_invalid_code(
        self, client: Client, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """Invalid TOTP code on confirm returns 400 invalid_code."""
        headers = _get_auth_headers(receptionist, tenant_a.schema_name)
        client.post("/api/v1/auth/totp/enroll", **headers)

        confirm_res = client.post(
            "/api/v1/auth/totp/enroll/confirm",
            data={"code": "000000"},
            content_type="application/json",
            **headers,
        )
        assert confirm_res.status_code == 400
        assert confirm_res.json()["error"]["code"] == "invalid_code"

    def test_totp_verify_happy_path_and_clock_drift(
        self, client: Client, owner: StaffUser, tenant_a: Any
    ) -> None:
        """Owner with enrolled TOTP logs in, completes challenge with clock drift."""
        # Setup TOTP on owner
        secret = pyotp.random_base32()
        fernet = Fernet(settings.LABFLOW_TOTP_ENCRYPTION_KEY.encode())
        encrypted_secret = fernet.encrypt(secret.encode()).decode()

        with schema_context(tenant_a.schema_name):
            owner.totp_secret_encrypted = encrypted_secret
            owner.totp_enabled = True
            owner.totp_backup_codes_hash = [make_password("BACKUP01")]
            owner.save()

        # Step 1: Login with password -> returns totp_required and sets challenge cookie
        login_res = client.post(
            "/api/v1/auth/login",
            data={"email": "owner@lab12.com", "password": "OwnerPasswordSecure123!"},
            content_type="application/json",
        )
        assert login_res.status_code == 200
        assert login_res.json()["totp_required"] is True
        assert "auth_challenge" in login_res.cookies
        challenge_token = login_res.cookies["auth_challenge"].value

        # Step 2: Verify with TOTP code (+1 window drift)
        totp = pyotp.TOTP(secret)
        code = totp.now()

        verify_res = client.post(
            "/api/v1/auth/totp/verify",
            data={"code": code},
            content_type="application/json",
        )
        assert verify_res.status_code == 200
        verify_data = verify_res.json()
        assert "access" in verify_data
        assert "refresh_token" in verify_res.cookies
        # Challenge cookie cleared
        assert verify_res.cookies["auth_challenge"].value == ""

    def test_totp_verify_with_single_use_backup_code(
        self, client: Client, owner: StaffUser, tenant_a: Any
    ) -> None:
        """Doc 08 §4.4: Backup code logs in, single-use removes its hash."""
        secret = pyotp.random_base32()
        fernet = Fernet(settings.LABFLOW_TOTP_ENCRYPTION_KEY.encode())
        encrypted_secret = fernet.encrypt(secret.encode()).decode()
        backup_code = "SECRET-CODE-01"

        with schema_context(tenant_a.schema_name):
            owner.totp_secret_encrypted = encrypted_secret
            owner.totp_enabled = True
            owner.totp_backup_codes_hash = [make_password(backup_code), make_password("CODE2")]
            owner.save()

        # Step 1: Login -> Challenge
        client.post(
            "/api/v1/auth/login",
            data={"email": "owner@lab12.com", "password": "OwnerPasswordSecure123!"},
            content_type="application/json",
        )

        # Step 2: Verify with backup code
        verify_res = client.post(
            "/api/v1/auth/totp/verify",
            data={"code": backup_code, "is_backup_code": True},
            content_type="application/json",
        )
        assert verify_res.status_code == 200
        assert "access" in verify_res.json()

        # Verify hash was consumed (only 1 remaining)
        with schema_context(tenant_a.schema_name):
            u = StaffUser.objects.get(id=owner.id)
            assert len(u.totp_backup_codes_hash) == 1

        # Re-using the same backup code fails
        client.post(
            "/api/v1/auth/login",
            data={"email": "owner@lab12.com", "password": "OwnerPasswordSecure123!"},
            content_type="application/json",
        )
        reuse_res = client.post(
            "/api/v1/auth/totp/verify",
            data={"code": backup_code},
            content_type="application/json",
        )
        assert reuse_res.status_code == 401

    def test_totp_challenge_expires_after_5_failed_attempts(
        self, client: Client, owner: StaffUser, tenant_a: Any
    ) -> None:
        """Doc 08 §4.4: 5 failed attempts destroy challenge -> 401 totp_challenge_expired."""
        with schema_context(tenant_a.schema_name):
            owner.totp_enabled = True
            owner.save()

        client.post(
            "/api/v1/auth/login",
            data={"email": "owner@lab12.com", "password": "OwnerPasswordSecure123!"},
            content_type="application/json",
        )

        # 4 failed attempts
        for _ in range(4):
            res = client.post(
                "/api/v1/auth/totp/verify",
                data={"code": "999999"},
                content_type="application/json",
            )
            assert res.status_code == 401
            assert res.json()["error"]["code"] == "invalid_credentials"

        # 5th failed attempt destroys challenge
        res5 = client.post(
            "/api/v1/auth/totp/verify",
            data={"code": "999999"},
            content_type="application/json",
        )
        assert res5.status_code == 401
        assert res5.json()["error"]["code"] == "totp_challenge_expired"

    def test_owner_resets_staff_totp(
        self, client: Client, owner: StaffUser, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """Doc 08 §4.4, LAB-52: Owner resets staff TOTP -> clears secret and codes."""
        # Set receptionist with TOTP enrolled
        with schema_context(tenant_a.schema_name):
            receptionist.totp_enabled = True
            receptionist.totp_secret_encrypted = "dummy"
            receptionist.totp_backup_codes_hash = ["hash1"]
            receptionist.save()

        owner_headers = _get_auth_headers(owner, tenant_a.schema_name)
        reset_res = client.post(
            f"/api/v1/staff/{receptionist.id}/reset-totp",
            **owner_headers,
        )
        assert reset_res.status_code == 200

        with schema_context(tenant_a.schema_name):
            rec = StaffUser.objects.get(id=receptionist.id)
            assert rec.totp_enabled is False
            assert rec.totp_secret_encrypted is None
            assert rec.totp_backup_codes_hash is None

            # Verify audit log
            audit = AuditLog.objects.filter(
                actor_id=owner.id,
                action="auth.totp_reset",
            ).first()
            assert audit is not None
            assert str(audit.entity_id) == str(receptionist.id)
