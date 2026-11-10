"""Tests for temporary-password flow and self-service TOTP disable.

Covers the LAB-62 additions:
1. Login surfaces ``must_change_password`` for accounts still on the
   provisioning-issued temporary master password.
2. Password change clears ``password_is_temporary`` and wipes the tenant-level
   ``temp_password`` / ``temp_password_expires_at`` from the public registry.
3. Self-service TOTP disable requires the current password and clears the
   enrolled secret / backup codes.
"""

from typing import Any

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client
from django_tenants.utils import schema_context

from apps.accounts.models import Role, StaffUser
from apps.core.models import Tenant


@pytest.fixture
def client_tenant_a(tenant_a: Any) -> Client:
    """HTTP client bound to tenant_a host."""
    return Client(HTTP_HOST="tenant-a.localhost")


@pytest.fixture
def temporary_password_owner(tenant_a: Any) -> StaffUser:
    """Lab Owner still on the provisioning-issued temporary password."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="owner_temp@labflow.local",
            password_hash=make_password("TempMaster123!"),
            role=Role.OWNER,
            is_active=True,
            password_is_temporary=True,
            totp_enabled=False,
        )


@pytest.mark.django_db
@pytest.mark.tenancy
class TestTemporaryPasswordFlow:
    def test_login_surfaces_must_change_password(
        self,
        client_tenant_a: Client,
        temporary_password_owner: StaffUser,
    ) -> None:
        """A temporary-credential account gets must_change_password on login."""
        res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": temporary_password_owner.email,
                "password": "TempMaster123!",
            },
            content_type="application/json",
        )

        assert res.status_code == 200
        data = res.json()
        assert data["user"]["must_change_password"] is True

    def test_change_password_clears_flag_and_tenant_temp_password(
        self,
        client_tenant_a: Client,
        temporary_password_owner: StaffUser,
        tenant_a: Any,
    ) -> None:
        """Changing the password invalidates the temporary credential."""
        # Seed the platform registry with the temporary credential.
        with schema_context("public"):
            Tenant.objects.filter(schema_name=tenant_a.schema_name).update(
                temp_password="LBF-ABCD-EF#",
            )

        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={
                "email": temporary_password_owner.email,
                "password": "TempMaster123!",
            },
            content_type="application/json",
        )
        access_token = login_res.json()["access"]

        change_res = client_tenant_a.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "TempMaster123!",
                "new_password": "BrandNewPassword456!",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert change_res.status_code == 200

        with schema_context(tenant_a.schema_name):
            owner = StaffUser.objects.get(id=temporary_password_owner.id)
            assert owner.password_is_temporary is False
            from django.contrib.auth.hashers import check_password

            assert check_password("BrandNewPassword456!", owner.password_hash)

        with schema_context("public"):
            tenant = Tenant.objects.get(schema_name=tenant_a.schema_name)
            assert tenant.temp_password == ""
            assert tenant.temp_password_expires_at is None


@pytest.mark.django_db
@pytest.mark.tenancy
class TestTotpDisable:
    def test_disable_totp_requires_password_and_clears_secret(
        self,
        client_tenant_a: Client,
        tenant_a: Any,
    ) -> None:
        """Disable requires the correct password and strips TOTP material."""
        import pyotp
        from cryptography.fernet import Fernet
        from django.conf import settings

        raw_secret = pyotp.random_base32()
        fernet = Fernet(settings.LABFLOW_TOTP_ENCRYPTION_KEY.encode())
        encrypted_secret = fernet.encrypt(raw_secret.encode()).decode()

        with schema_context(tenant_a.schema_name):
            user = StaffUser.objects.create(
                email="selfserve@labflow.local",
                password_hash=make_password("SelfServePass123!"),
                role=Role.OWNER,
                is_active=True,
                totp_enabled=True,
                totp_secret_encrypted=encrypted_secret,
                totp_backup_codes_hash=[make_password("BACKUP-01")],
            )

        # Login -> TOTP challenge -> verify to obtain an access token.
        login_res = client_tenant_a.post(
            "/api/v1/auth/login",
            data={"email": user.email, "password": "SelfServePass123!"},
            content_type="application/json",
        )
        challenge_token = login_res.json()["challenge_token"]

        client_tenant_a.cookies["auth_challenge"] = challenge_token
        verify_res = client_tenant_a.post(
            "/api/v1/auth/totp/verify",
            data={"code": pyotp.TOTP(raw_secret).now()},
            content_type="application/json",
        )
        access_token = verify_res.json()["access"]

        # Wrong password rejected.
        bad_res = client_tenant_a.post(
            "/api/v1/auth/totp/disable",
            data={"current_password": "WrongPassword123!"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert bad_res.status_code == 401
        assert bad_res.json()["error"]["code"] == "invalid_credentials"

        # Correct password disables TOTP.
        ok_res = client_tenant_a.post(
            "/api/v1/auth/totp/disable",
            data={"current_password": "SelfServePass123!"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert ok_res.status_code == 200

        with schema_context(tenant_a.schema_name):
            updated = StaffUser.objects.get(id=user.id)
            assert updated.totp_enabled is False
            assert updated.totp_secret_encrypted is None
            assert updated.totp_backup_codes_hash is None
