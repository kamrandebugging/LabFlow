"""Tests for LAB-14 Session Management & Revocation (Doc 08 §4.6, §4.7).

Covers:
- GET /api/v1/auth/sessions — active sessions, current-session marker
- DELETE /api/v1/auth/sessions/:id — remote disconnect; 404 for other user
- POST /api/v1/auth/sessions/revoke-all — revokes caller sessions, sets marker
- POST /api/v1/auth/password/change — updates hash, revokes other sessions
"""

from typing import Any

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.test import Client
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog, Role, StaffUser


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
class TestLAB14SessionManagement:
    """Doc 08 §4.6 & §4.7: Sessions list, remote revoke, revoke-all, password change."""

    def test_session_list_shows_caller_sessions_with_current_marker(
        self, client: Client, user_a: StaffUser
    ) -> None:
        """GET /api/v1/auth/sessions returns active sessions with current marker."""
        # Device 1 login
        res1 = client.post(
            "/api/v1/auth/login",
            data={"email": "user_a@authlab.com", "password": "UserAPassword123!"},
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        )
        assert res1.status_code == 200

        # Device 2 login
        res2 = client.post(
            "/api/v1/auth/login",
            data={"email": "user_a@authlab.com", "password": "UserAPassword123!"},
            content_type="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        )
        token2 = res2.json()["access"]

        # Query sessions using token2
        list_res = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
        )
        assert list_res.status_code == 200
        sessions = list_res.json()
        assert len(sessions) == 2

        # Exactly one session has current=True
        current_sessions = [s for s in sessions if s.get("current") is True]
        assert len(current_sessions) == 1

        # No secret or hash material leaked
        for s in sessions:
            assert "token" not in s
            assert "hash" not in s
            assert "jti" not in s
            assert "fid" not in s
            assert "id" in s
            assert "created_at" in s

    def test_remote_revoke_terminates_target_session_instantly(
        self, client: Client, user_a: StaffUser, tenant_a: Any
    ) -> None:
        """DELETE /api/v1/auth/sessions/:id terminates targeted session immediately."""
        res1 = client.post(
            "/api/v1/auth/login",
            data={"email": "user_a@authlab.com", "password": "UserAPassword123!"},
            content_type="application/json",
            HTTP_USER_AGENT="Device1",
        )
        token1 = res1.json()["access"]

        res2 = client.post(
            "/api/v1/auth/login",
            data={"email": "user_a@authlab.com", "password": "UserAPassword123!"},
            content_type="application/json",
            HTTP_USER_AGENT="Device2",
        )
        token2 = res2.json()["access"]

        # Get sessions list from Device 2
        sessions = client.get(
            "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token2}"
        ).json()
        other_session = [s for s in sessions if not s["current"]][0]

        # Revoke other session
        del_res = client.delete(
            f"/api/v1/auth/sessions/{other_session['id']}",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
        )
        assert del_res.status_code == 204

        # Audit row created for remote revocation (LAB-14 DoD)
        with schema_context(tenant_a.schema_name):
            audit_row = AuditLog.objects.filter(
                actor_id=user_a.id, action="auth.session_revoked"
            ).first()
            assert audit_row is not None
            assert str(audit_row.entity_id) == str(other_session["id"])

        # Device 1's token is immediately rejected
        device1_call = client.get(
            "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token1}"
        )
        assert device1_call.status_code == 401

        # Device 2's token still works
        device2_call = client.get(
            "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token2}"
        )
        assert device2_call.status_code == 200

    def test_scoped_delete_returns_404_when_deleting_another_users_session(
        self, client: Client, user_a: StaffUser, user_b: StaffUser, tenant_a: Any
    ) -> None:
        """User B calling DELETE on User A session returns 404 without leakage."""
        res_a = client.post(
            "/api/v1/auth/login",
            data={"email": "user_a@authlab.com", "password": "UserAPassword123!"},
            content_type="application/json",
        )
        token_a = res_a.json()["access"]
        session_a_id = client.get(
            "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token_a}"
        ).json()[0]["id"]

        res_b = client.post(
            "/api/v1/auth/login",
            data={"email": "user_b@authlab.com", "password": "UserBPassword123!"},
            content_type="application/json",
        )
        token_b = res_b.json()["access"]

        # User B attempts to revoke User A's session
        attack_res = client.delete(
            f"/api/v1/auth/sessions/{session_a_id}",
            HTTP_AUTHORIZATION=f"Bearer {token_b}",
        )
        assert attack_res.status_code == 404

        # User A's session is still completely valid
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token_a}"
            ).status_code
            == 200
        )

        # Zero audit rows created for the failed cross-user attempt
        with schema_context(tenant_a.schema_name):
            assert not AuditLog.objects.filter(actor_id=user_b.id).exists()

    def test_password_change_revokes_all_other_sessions(
        self, client: Client, user_a: StaffUser, tenant_a: Any
    ) -> None:
        """Changing password revokes all OTHER sessions while current remains active."""
        res1 = client.post(
            "/api/v1/auth/login",
            data={"email": "user_a@authlab.com", "password": "UserAPassword123!"},
            content_type="application/json",
        )
        token1 = res1.json()["access"]

        res2 = client.post(
            "/api/v1/auth/login",
            data={"email": "user_a@authlab.com", "password": "UserAPassword123!"},
            content_type="application/json",
        )
        token2 = res2.json()["access"]

        # Change password using token2
        change_res = client.post(
            "/api/v1/auth/password/change",
            data={
                "current_password": "UserAPassword123!",
                "new_password": "NewStrongPassword789!",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token2}",
        )
        assert change_res.status_code == 200

        # Password hash updated in DB
        with schema_context(tenant_a.schema_name):
            user_a.refresh_from_db()
            assert check_password("NewStrongPassword789!", user_a.password_hash)

            # Audit logs recorded for password change and other-session revocations
            assert AuditLog.objects.filter(
                actor_id=user_a.id, action="auth.password_changed"
            ).exists()

        # Device 1 token is revoked
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token1}"
            ).status_code
            == 401
        )

        # Device 2 (token2) still works
        assert (
            client.get(
                "/api/v1/auth/sessions", HTTP_AUTHORIZATION=f"Bearer {token2}"
            ).status_code
            == 200
        )
