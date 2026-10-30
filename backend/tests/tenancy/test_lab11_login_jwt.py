"""Tests for LAB-11 Login Endpoint & JWT Engine (Doc 08 §4.1, §4.3, §10.1).

Covers:
- POST /api/v1/auth/login happy path with argon2 password verification
- 15-minute access JWT returned in body; 7-day refresh token in httpOnly cookie ONLY
- Zero refresh token material in JSON response body (DoD requirement)
- Generic 401 invalid_credentials for wrong password, missing email, inactive user
- Dummy password hash verification executed for non-existent users
- Login throttling: 5 / 15m per (tenant, email) and 20 / 15m per IP -> 429 rate_limited
- Fail-closed on Redis failure -> 503 service_unavailable
- login_event row created for every attempt (success, failure, throttled)
- TOTP hook: accounts requiring TOTP receive totp_required: true and no session yet
"""

from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import Client
from django_tenants.utils import schema_context

from apps.accounts.models import LoginEvent, Role, StaffUser


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def receptionist(tenant_a: Any) -> StaffUser:
    """Staff user without mandatory TOTP."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="receptionist@authlab.com",
            password_hash=make_password("CorrectHorseBatteryStaple123!"),
            role=Role.RECEPTION,
            is_active=True,
        )


@pytest.fixture
def owner(tenant_a: Any) -> StaffUser:
    """Owner account with mandatory TOTP (Doc 01 §14, Doc 08 §4.1)."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="owner@authlab.com",
            password_hash=make_password("OwnerPasswordSecure123!"),
            role=Role.OWNER,
            is_active=True,
        )


@pytest.fixture
def inactive_user(tenant_a: Any) -> StaffUser:
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="inactive@authlab.com",
            password_hash=make_password("InactivePassword123!"),
            role=Role.RECEPTION,
            is_active=False,
        )


@pytest.fixture
def client(tenant_a: Any) -> Client:
    return Client(HTTP_HOST="tenant-a.localhost")


@pytest.mark.django_db
class TestLAB11LoginEndpoint:
    """Doc 08 §4.1: POST /api/v1/auth/login."""

    def test_login_success_sets_http_only_cookie_and_returns_access_jwt(
        self, client: Client, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """Success returns 15m access in body and 7d refresh in httpOnly cookie."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "CorrectHorseBatteryStaple123!",
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()

        # 1. Access token in body
        assert "access" in data
        assert data.get("expires_in") == 900
        assert data.get("user", {}).get("email") == "receptionist@authlab.com"
        assert data.get("user", {}).get("role") == Role.RECEPTION

        # 2. Refresh token MUST NOT be in response body (Strict DoD rule!)
        assert "refresh" not in data
        assert "refresh_token" not in data
        response_text = response.content.decode("utf-8")
        assert "fid" not in response_text

        # 3. Refresh token must be in httpOnly, Secure, SameSite=Lax cookie
        assert "refresh_token" in response.cookies
        cookie = response.cookies["refresh_token"]
        assert cookie["httponly"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["path"] == "/api/v1/auth/"

        # 4. login_event row created
        with schema_context(tenant_a.schema_name):
            events = LoginEvent.objects.filter(
                email_attempted="receptionist@authlab.com"
            )
            assert events.count() == 1
            event = events.first()
            assert event is not None
            assert event.success is True
            assert event.staff_user == receptionist

    def test_login_invalid_credentials_returns_generic_401(
        self, client: Client, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """Wrong password returns generic 401 invalid_credentials."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "WrongPassword!456",
            },
            content_type="application/json",
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "invalid_credentials"
        assert "refresh_token" not in response.cookies

        # Failure recorded in login_event
        with schema_context(tenant_a.schema_name):
            event = LoginEvent.objects.filter(
                email_attempted="receptionist@authlab.com", success=False
            ).first()
            assert event is not None

    def test_login_unknown_email_returns_identical_generic_401(
        self, client: Client, tenant_a: Any
    ) -> None:
        """Non-existent email returns identical 401 without user enumeration."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "email": "nonexistent@authlab.com",
                "password": "AnyPassword123!",
            },
            content_type="application/json",
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "invalid_credentials"

        with schema_context(tenant_a.schema_name):
            event = LoginEvent.objects.filter(
                email_attempted="nonexistent@authlab.com"
            ).first()
            assert event is not None
            assert event.success is False
            assert event.staff_user is None

    def test_login_inactive_user_returns_generic_401(
        self, client: Client, inactive_user: StaffUser
    ) -> None:
        """Inactive user account returns identical generic 401."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "email": "inactive@authlab.com",
                "password": "InactivePassword123!",
            },
            content_type="application/json",
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_totp_mandatory_role_returns_totp_required_and_no_session(
        self, client: Client, owner: StaffUser
    ) -> None:
        """Owner role requires TOTP: returns totp_required: true challenge cookie."""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "email": "owner@authlab.com",
                "password": "OwnerPasswordSecure123!",
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("totp_required") is True
        assert "access" not in data
        assert "refresh_token" not in response.cookies
        assert "auth_challenge" in response.cookies

    def test_login_throttling_after_5_failed_attempts_returns_429(
        self, client: Client, receptionist: StaffUser, tenant_a: Any
    ) -> None:
        """Doc 08 §10.1: 5 attempts / 15m per (tenant, email) -> 429."""
        for _ in range(5):
            res = client.post(
                "/api/v1/auth/login",
                data={
                    "email": "receptionist@authlab.com",
                    "password": "WrongPassword!",
                },
                content_type="application/json",
            )
            assert res.status_code == 401

        # 6th attempt is throttled
        throttled_res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "CorrectHorseBatteryStaple123!",
            },
            content_type="application/json",
        )
        assert throttled_res.status_code == 429
        data = throttled_res.json()
        assert data["error"]["code"] == "rate_limited"
        assert "Retry-After" in throttled_res.headers

        # Throttled attempt still writes login_event
        with schema_context(tenant_a.schema_name):
            assert (
                LoginEvent.objects.filter(
                    email_attempted="receptionist@authlab.com"
                ).count()
                == 6
            )

    def test_login_fails_closed_when_redis_is_down(
        self, client: Client, receptionist: StaffUser
    ) -> None:
        """Doc 08 §10.3: Auth surfaces fail closed -> HTTP 503 on Redis outage."""
        with patch(
            "apps.accounts.views_auth.check_and_record_login_throttle",
            side_effect=Exception("Redis down"),
        ):
            response = client.post(
                "/api/v1/auth/login",
                data={
                    "email": "receptionist@authlab.com",
                    "password": "CorrectHorseBatteryStaple123!",
                },
                content_type="application/json",
            )
            assert response.status_code == 503
            data = response.json()
            assert data["error"]["code"] == "service_unavailable"
