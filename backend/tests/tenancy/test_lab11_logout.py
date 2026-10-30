"""Tests for LAB-11 Logout Endpoint (Doc 08 §4.1, §4.3, SE-07).

Covers:
- POST /api/v1/auth/logout requires Bearer access token + refresh cookie
- Denylists refresh token jti and paired access token jti
- Clears refresh cookie with expired Set-Cookie
- Subsequent access with the same access token is rejected immediately (SE-07)
- Returns 204 No Content
"""

from typing import Any

import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import Client
from django_tenants.utils import schema_context

from apps.accounts.models import Role, StaffUser


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
class TestLAB11Logout:
    """Doc 08 §4.1 & §4.3: POST /api/v1/auth/logout."""

    def test_logout_denylists_tokens_and_clears_cookie_instantly(
        self, client: Client, receptionist: StaffUser
    ) -> None:
        """Logout immediately revokes tokens so subsequent authenticated calls fail."""
        login_res = client.post(
            "/api/v1/auth/login",
            data={
                "email": "receptionist@authlab.com",
                "password": "CorrectHorseBatteryStaple123!",
            },
            content_type="application/json",
        )
        assert login_res.status_code == 200
        access_token = login_res.json()["access"]
        refresh_cookie = login_res.cookies["refresh_token"].value

        # Authenticated call before logout succeeds
        client.cookies["refresh_token"] = refresh_cookie
        sessions_res = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert sessions_res.status_code == 200

        # Logout
        logout_res = client.post(
            "/api/v1/auth/logout",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert logout_res.status_code == 204
        assert logout_res.cookies["refresh_token"]["max-age"] == 0

        # SE-07: Next call with the access token is rejected instantly
        after_logout_res = client.get(
            "/api/v1/auth/sessions",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert after_logout_res.status_code == 401

        # Refresh with old cookie also fails
        refresh_after_logout = client.post("/api/v1/auth/refresh")
        assert refresh_after_logout.status_code == 401
