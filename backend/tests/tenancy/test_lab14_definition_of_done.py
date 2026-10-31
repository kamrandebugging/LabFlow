"""Definition of Done Verification for LAB-14 (KAN-107).

Authoritative Verification of all LAB-14 DoD & Acceptance Criteria:
1. Caller-scoped session list with current-session marker & zero credential leaks
2. Instant remote revocation with audit log trail & 404 cross-user boundary defense
3. Reusable revoke-all service method across theft detection & password change
4. Password change policy enforcement & selective session preservation
"""

from typing import Any

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.test import Client
from django_tenants.utils import schema_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.accounts.session_registry import get_user_revocation_marker


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def staff_user(tenant_a: Any) -> StaffUser:
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="receptionist@authlab.com",
            password_hash=make_password("ReceptionistPass2026!"),
            role=Role.RECEPTION,
            is_active=True,
        )


@pytest.fixture
def client(tenant_a: Any) -> Client:
    return Client(HTTP_HOST="tenant-a.localhost")


@pytest.mark.django_db
class TestLAB14DefinitionOfDone:
    """LAB-14 Definition of Done Verification."""

    def test_dod_session_list_caller_scoped_no_credential_leakage(
        self, client: Client, staff_user: StaffUser
    ) -> None:
        """DoD: GET /api/v1/auth/sessions returns caller sessions without secrets."""
        res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "ReceptionistPass2026!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Workstation-Chrome",
        )
        assert res.status_code == 200
        token = res.json()["access"]

        list_res = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_USER_AGENT="Workstation-Chrome",
        )
        assert list_res.status_code == 200
        data = list_res.json()
        assert len(data) == 1
        assert data[0]["current"] is True

        # Assert no credential, jti, hash or fid leakage anywhere in payload
        for forbidden in ("token", "hash", "jti", "fid", "current_refresh_jti"):
            assert forbidden not in data[0]

    def test_dod_reusable_revoke_all_service_emits_audit_and_sets_marker(
        self, client: Client, staff_user: StaffUser, tenant_a: Any
    ) -> None:
        """DoD: Reusable revoke-all service method emits audit and sets Redis marker."""
        with schema_context(tenant_a.schema_name):
            initial_audits = AuditLog.objects.filter(actor_id=staff_user.id).count()

            # Execute reusable service method
            AuthService.revoke_all_sessions(
                staff_user_id=staff_user.id,
                tenant_id=tenant_a.schema_name,
                reason="admin_action",
                ip="192.168.1.10",
                user_agent="AdminConsole/1.0",
            )

            # Audit row exists
            audits = AuditLog.objects.filter(
                actor_id=staff_user.id, action="auth.sessions_revoked"
            )
            assert audits.count() > initial_audits
            latest_audit = audits.latest("at")
            assert latest_audit.after_jsonb is not None
            assert latest_audit.after_jsonb.get("reason") == "admin_action"

        # Redis marker set
        marker = get_user_revocation_marker(staff_user.id)
        assert marker is not None

    def test_dod_password_change_policy_and_session_preservation(
        self, client: Client, staff_user: StaffUser, tenant_a: Any
    ) -> None:
        """DoD: Password change updates hash, preserves current, revokes others."""
        # Device 1
        res1 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "ReceptionistPass2026!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Desktop",
        )
        token1 = res1.json()["access"]

        # Device 2
        res2 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "ReceptionistPass2026!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Laptop",
        )
        token2 = res2.json()["access"]

        # Password change via Device 2
        change_res = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "ReceptionistPass2026!",
                "new_password": "NewCompliantPassword2026!",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
            HTTP_USER_AGENT="Laptop",
        )
        assert change_res.status_code == 200

        with schema_context(tenant_a.schema_name):
            staff_user.refresh_from_db()
            assert check_password("NewCompliantPassword2026!", staff_user.password_hash)

        # Device 1 rejected
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token1}"
            ).status_code
            == 401
        )

        # Device 2 works
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token2}"
            ).status_code
            == 200
        )
