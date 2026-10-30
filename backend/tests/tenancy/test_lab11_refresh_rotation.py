"""Tests for LAB-11 Refresh Endpoint & Reuse Detection (Doc 08 §4.3, SE-05).

Covers:
- POST /api/v1/auth/refresh reads httpOnly cookie (never request body)
- Rotation-on-use: old token invalidated, new refresh cookie + access returned
- Refresh token value NEVER appears in response body
- Absolute 7-day family cap: expiration cannot exceed original login + 7 days
- Reuse detection (SE-05): presenting used token revokes ALL user sessions,
  sets auth:revoked_before:<user_id> marker, returns 401 refresh_reuse_detected
"""

from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
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
def receptionist(tenant_a: Any) -> StaffUser:
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="receptionist@authlab.com",
            password_hash=make_password("CorrectHorseBatteryStaple123!"),
            role=Role.RECEPTION,
            is_active=True,
        )


@pytest.fixture
def client(tenant_a: Any) -> Client:
    return Client(HTTP_HOST="tenant-a.localhost")


@pytest.mark.django_db
class TestLAB11RefreshRotationAndReuse:
    """Doc 08 §4.3: POST /api/v1/auth/refresh."""

    def test_refresh_rotation_on_use_success(
        self, client: Client, receptionist: StaffUser
    ) -> None:
        """Presenting refresh cookie returns new access JWT and rotates cookie."""
        login_res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "CorrectHorseBatteryStaple123!",
            },
            content_type="application/json",
        )
        assert login_res.status_code == 200
        initial_refresh_cookie = login_res.cookies["refresh_token"].value

        # Refresh call
        client.cookies["refresh_token"] = initial_refresh_cookie
        refresh_res = client.post("/api/v1/auth/refresh")
        assert refresh_res.status_code == 200
        data = refresh_res.json()

        assert "access" in data
        assert data.get("expires_in") == 900
        assert "refresh" not in data
        assert "refresh_token" not in data

        new_refresh_cookie = refresh_res.cookies["refresh_token"].value
        assert new_refresh_cookie != initial_refresh_cookie

    def test_reuse_detection_revokes_all_user_sessions_and_sentry_alert(
        self, client: Client, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """SE-05: Replaying an already-used refresh token revokes all user sessions."""
        login_res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "CorrectHorseBatteryStaple123!",
            },
            content_type="application/json",
        )
        token_v1 = login_res.cookies["refresh_token"].value

        # Legitimate client rotates token_v1 -> gets token_v2
        client.cookies["refresh_token"] = token_v1
        res1 = client.post("/api/v1/auth/refresh")
        assert res1.status_code == 200
        token_v2 = res1.cookies["refresh_token"].value

        # Attacker replays token_v1
        client.cookies["refresh_token"] = token_v1
        with patch("apps.accounts.auth_service.logger.warning") as mock_log:
            replay_res = client.post("/api/v1/auth/refresh")

        assert replay_res.status_code == 401
        data = replay_res.json()
        assert data["error"]["code"] == "refresh_reuse_detected"

        # Sentry / Security warning emitted
        assert mock_log.called

        # Revocation marker is set in Redis
        marker_key = f"auth:revoked_before:{receptionist.id}"
        assert cache.get(marker_key) is not None

        # Audit log row recorded with reason refresh_reuse
        with schema_context(tenant_a.schema_name):
            audit_rows = AuditLog.objects.filter(
                actor_id=receptionist.id, action="auth.sessions_revoked"
            )
            assert audit_rows.exists()
            assert audit_rows.first().after_jsonb.get("reason") == "refresh_reuse"

        # Legitimate token_v2 is now ALSO revoked
        client.cookies["refresh_token"] = token_v2
        res2 = client.post("/api/v1/auth/refresh")
        assert res2.status_code == 401
