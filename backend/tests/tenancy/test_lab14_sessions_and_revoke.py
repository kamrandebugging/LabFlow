"""Tests for LAB-14 Session Management & Revocation (Doc 08 §4.6, §4.7 / KAN-107).

Subtasks covered:
- KAN-108: GET /api/v1/auth/sessions — caller-scoped, current-session marker
- KAN-109: DELETE /api/v1/auth/sessions/:id — remote disconnect; 404 for other
- KAN-110: POST /api/v1/auth/sessions/revoke-all & POST /api/v1/auth/password/change
- KAN-111: Security Verification Checklist (SE requirements)
"""

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.test import Client
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.accounts.session_registry import (
    get_user_revocation_marker,
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user_a(tenant_a: Any) -> StaffUser:
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="user_a@authlab.com",
            password_hash=make_password("UserAPassword123!"),
            role=Role.RECEPTION,
            is_active=True,
        )


@pytest.fixture
def user_b(tenant_a: Any) -> StaffUser:
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="user_b@authlab.com",
            password_hash=make_password("UserBPassword123!"),
            role=Role.TECHNICIAN,
            is_active=True,
        )


@pytest.fixture
def client(tenant_a: Any) -> Client:
    return Client(HTTP_HOST="tenant-a.localhost")


@pytest.mark.django_db
class TestLAB14SessionManagementAndRevocation:
    """Doc 08 §4.6 & §4.7: Sessions list, remote revoke, revoke-all."""

    def test_kan108_session_list_caller_scoped_with_current_marker(
        self, client: Client, user_a: StaffUser
    ) -> None:
        """KAN-108: GET /auth/sessions returns caller sessions with marker."""
        # Device 1 login
        res1 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Device-Firefox-Linux",
        )
        assert res1.status_code == 200

        # Device 2 login
        res2 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Device-Safari-iOS",
        )
        assert res2.status_code == 200
        token2 = res2.json()["access"]

        # Request session list using Device 2's token
        list_res = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
            HTTP_USER_AGENT="Device-Safari-iOS",
        )
        assert list_res.status_code == 200
        sessions = list_res.json()
        assert len(sessions) == 2

        # Exactly one session has current=True matching Device 2
        current_sessions = [s for s in sessions if s.get("current") is True]
        assert len(current_sessions) == 1
        assert current_sessions[0]["user_agent"] == "Device-Safari-iOS"

        # Verification of Doc 08 §4.7 fields and zero secret material leak
        for s in sessions:
            assert "id" in s
            assert "ip" in s
            assert "user_agent" in s
            assert "created_at" in s
            assert "last_active" in s
            assert "token" not in s
            assert "hash" not in s
            assert "jti" not in s
            assert "fid" not in s

    def test_kan109_remote_revoke_terminates_session_instantly_with_audit(
        self, client: Client, user_a: StaffUser, tenant_a: Any
    ) -> None:
        """KAN-109: DELETE /auth/sessions/:id terminates session instantly."""
        # Device 1 login
        res1 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Device1",
        )
        token1 = res1.json()["access"]
        cookie1 = res1.cookies["refresh_token"].value

        # Device 2 login
        res2 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Device2",
        )
        token2 = res2.json()["access"]

        # Fetch sessions from Device 2
        sessions = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
            HTTP_USER_AGENT="Device2",
        ).json()
        other_session = next(s for s in sessions if not s["current"])

        # Revoke Device 1 from Device 2
        del_res = client.delete(
            f"/api/v1/auth/sessions/{other_session['id']}",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
        )
        assert del_res.status_code == 204

        # Verify audit row created in tenant schema
        with schema_context(tenant_a.schema_name):
            audit = AuditLog.objects.filter(
                actor_id=user_a.id, action="auth.session_revoked"
            ).first()
            assert audit is not None
            assert str(audit.entity_id) == str(other_session["id"])

        # Device 1 access token is immediately rejected with 401
        probe1 = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {token1}",
        )
        assert probe1.status_code == 401

        # Device 2 remains completely functional
        probe2 = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
        )
        assert probe2.status_code == 200

        # Device 1 refresh cookie is also rejected (triggers SE-05 reuse)
        client.cookies["refresh_token"] = cookie1
        refresh_probe = client.post("/api/v1/auth/refresh")
        assert refresh_probe.status_code == 401

    def test_kan109_scoped_delete_returns_404_for_other_user_without_leakage(
        self,
        client: Client,
        user_a: StaffUser,
        user_b: StaffUser,
        tenant_a: Any,
    ) -> None:
        """KAN-109: Cross-user delete returns 404 and leaves target intact."""
        # User A login
        res_a = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
        )
        token_a = res_a.json()["access"]
        session_a_id = client.get(
            "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token_a}"
        ).json()[0]["id"]

        # User B login
        res_b = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_b@authlab.com",
                "password": "UserBPassword123!",
            },
            content_type="application/json",
        )
        token_b = res_b.json()["access"]

        # User B attempts to revoke User A's session
        attack_res = client.delete(
            f"/api/v1/auth/sessions/{session_a_id}",
            HTTP_AUTHORIZATION=f"Bearer {token_b}",
        )
        assert attack_res.status_code == 404
        assert attack_res.json()["error"]["code"] == "session_not_found"

        # Random non-existent UUID gives the exact same 404 response
        random_res = client.delete(
            f"/api/v1/auth/sessions/{uuid.uuid4()}",
            HTTP_AUTHORIZATION=f"Bearer {token_b}",
        )
        assert random_res.status_code == 404
        assert random_res.json() == attack_res.json()

        # User A's session is still completely valid
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token_a}"
            ).status_code
            == 200
        )

        # Zero audit rows created for the 404 attempt
        with schema_context(tenant_a.schema_name):
            assert not AuditLog.objects.filter(actor_id=user_b.id).exists()

    def test_kan110_revoke_all_sessions_invalidates_all_tokens_and_sets_marker(
        self, client: Client, user_a: StaffUser, tenant_a: Any
    ) -> None:
        """KAN-110: Revoke-all terminates all sessions and sets marker."""
        # Login 3 times
        tokens = []
        for i in range(3):
            res = client.post(
                "/api/v1/auth/login",
                data={
                    "email": "user_a@authlab.com",
                    "password": "UserAPassword123!",
                },
                content_type="application/json",
                HTTP_USER_AGENT=f"ClientDevice-{i}",
            )
            assert res.status_code == 200
            tokens.append(res.json()["access"])

        # Call revoke-all with token 3
        revoke_res = client.post(
            "/api/v1/auth/sessions/revoke-all",
            HTTP_AUTHORIZATION=f"Bearer {tokens[2]}",
        )
        assert revoke_res.status_code == 204

        # Redis marker set for user_a
        marker = get_user_revocation_marker(user_a.id)
        assert marker is not None

        # All 3 access tokens fail on next request
        for tok in tokens:
            probe = client.get(
                "/api/v1/auth/sessions",
                HTTP_AUTHORIZATION=f"Bearer {tok}",
            )
            assert probe.status_code == 401

        # Audit row created
        with schema_context(tenant_a.schema_name):
            assert AuditLog.objects.filter(
                actor_id=user_a.id, action="auth.sessions_revoked"
            ).exists()

    def test_kan110_password_change_policy_enforcement(
        self, client: Client, user_a: StaffUser
    ) -> None:
        """KAN-110: Password change strictly enforces Doc 08 §4.5 policy."""
        res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
        )
        token = res.json()["access"]

        # Case 1: Password too short (<12 chars)
        short_res = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "UserAPassword123!",
                "new_password": "Short1!",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert short_res.status_code == 422
        assert short_res.json()["error"]["code"] == "password_too_short"

        # Case 2: Password matches email
        email_res = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "UserAPassword123!",
                "new_password": "user_a@authlab.com",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert email_res.status_code == 422
        assert email_res.json()["error"]["code"] == "password_matches_email"

        # Case 3: Common password
        common_res = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "UserAPassword123!",
                "new_password": "password12345",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert common_res.status_code == 422
        assert common_res.json()["error"]["code"] == "password_too_common"

    def test_kan110_password_change_revokes_all_other_sessions(
        self, client: Client, user_a: StaffUser, tenant_a: Any
    ) -> None:
        """KAN-110: Changing password revokes all other sessions."""
        res1 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Device-1-Workstation",
        )
        token1 = res1.json()["access"]

        res2 = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
            HTTP_USER_AGENT="Device-2-Mobile",
        )
        token2 = res2.json()["access"]

        # Change password via Device 2
        change_res = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "UserAPassword123!",
                "new_password": "StrongNewValidPassword2026!",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
            HTTP_USER_AGENT="Device-2-Mobile",
        )
        assert change_res.status_code == 200

        # Password hash updated in database to Argon2id
        with schema_context(tenant_a.schema_name):
            user_a.refresh_from_db()
            assert check_password("StrongNewValidPassword2026!", user_a.password_hash)
            assert AuditLog.objects.filter(
                actor_id=user_a.id, action="auth.password_changed"
            ).exists()
            assert AuditLog.objects.filter(
                actor_id=user_a.id, action="auth.sessions_revoked"
            ).exists()

        # Login with old password fails
        login_old = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
        )
        assert login_old.status_code == 401

        # Login with new password succeeds
        login_new = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "StrongNewValidPassword2026!",
            },
            content_type="application/json",
        )
        assert login_new.status_code == 200

        # Device 1 token is revoked immediately
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token1}"
            ).status_code
            == 401
        )

        # Device 2 (the changing session) continues to work
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token2}"
            ).status_code
            == 200
        )

    def test_kan110_password_change_wrong_current_password_fails_generic(
        self, client: Client, user_a: StaffUser, tenant_a: Any
    ) -> None:
        """KAN-110: Wrong current password returns 401 generic failure."""
        res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
        )
        token = res.json()["access"]

        change_res = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "WrongPassword999!",
                "new_password": "ValidNewPassword2026!",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert change_res.status_code == 401
        assert change_res.json()["error"]["code"] == "invalid_credentials"

        # Password unchanged
        with schema_context(tenant_a.schema_name):
            user_a.refresh_from_db()
            assert check_password("UserAPassword123!", user_a.password_hash)

        # Existing session still valid
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token}"
            ).status_code
            == 200
        )

    def test_kan111_performance_single_scoped_redis_lookup(
        self, client: Client, user_a: StaffUser
    ) -> None:
        """KAN-111: GET /auth/sessions performs one caller lookup."""
        res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "user_a@authlab.com",
                "password": "UserAPassword123!",
            },
            content_type="application/json",
        )
        token = res.json()["access"]

        with patch("django.core.cache.cache.get", wraps=cache.get) as mock_get:
            res = client.get(
                "/api/v1/auth/sessions",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
            assert res.status_code == 200

            accessed_keys = [call[0][0] for call in mock_get.call_args_list]
            session_keys = [k for k in accessed_keys if "auth:sessions:" in k]
            assert len(session_keys) == 1
            assert str(user_a.id) in session_keys[0]
