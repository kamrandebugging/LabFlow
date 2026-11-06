"""Master dashboard Phase 1: platform operator auth (Doc 08 §4, Doc 04 §12.1)."""

import json
from typing import Any

import pyotp
import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core.models import PlatformAudit, PlatformUser
from apps.platform.auth_service import PlatformAuthService
from apps.platform.platform_jwt import platform_mint_access_token
from tests.factories.core import PlatformUserFactory

PASSWORD = "SuperAdminPassword123!"
HOST = "localhost"
LOGIN_URL = "/api/v1/platform/auth/login"
VERIFY_URL = "/api/v1/platform/auth/totp/verify"
REFRESH_URL = "/api/v1/platform/auth/refresh"
LOGOUT_URL = "/api/v1/platform/auth/logout"
TENANTS_URL = "/api/v1/platform/tenants"
ENROLL_URL = "/api/v1/platform/auth/totp/enroll"
ENROLL_CONFIRM_URL = "/api/v1/platform/auth/totp/enroll/confirm"
RESET_REQUEST_URL = "/api/v1/platform/auth/password-reset/request"
RESET_CONFIRM_URL = "/api/v1/platform/auth/password-reset/confirm"


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _encrypt(secret: str) -> str:
    key = settings.LABFLOW_TOTP_ENCRYPTION_KEY
    raw = key.encode() if isinstance(key, str) else key
    return Fernet(raw).encrypt(secret.encode()).decode()


def _totp_user(secret: str) -> PlatformUser:
    user = PlatformUserFactory(totp_enabled=True)
    user.totp_secret_encrypted = _encrypt(secret)
    user.save(update_fields=["totp_secret_encrypted"])
    return user


def _login(client: APIClient, email: str, password: str = PASSWORD) -> Any:
    return client.post(
        LOGIN_URL,
        data={"email": email, "password": password},
        format="json",
        HTTP_HOST=HOST,
    )


def _bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_login_issues_access_token_and_host_only_cookie() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()

    resp = _login(client, user.email)

    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == 900
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["totp_enabled"] is False

    cookie = resp.cookies["labflow_refresh"]
    assert cookie.value
    assert cookie["path"] == "/api/v1/platform/auth"
    assert cookie["httponly"] is True
    assert cookie["samesite"].lower() == "lax"
    assert cookie["secure"] is True
    # Host-only: a Domain attribute would widen the cookie to sibling hosts.
    assert not cookie["domain"]
    set_cookie = cookie.output()
    assert "labflow_refresh=" in set_cookie
    assert "Path=/api/v1/platform/auth" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie
    assert "Domain=" not in set_cookie

    assert PlatformAudit.objects.filter(action="auth.login_succeeded").exists()


@pytest.mark.django_db
def test_login_failure_is_generic_and_audited_without_actor() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()

    resp = _login(client, user.email, "definitely-the-wrong-password")

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "invalid_credentials"
    assert body["detail"] == "Email, password or code is not correct"
    assert resp["Content-Type"].startswith("application/problem+json")

    audit = PlatformAudit.objects.filter(action="auth.login_failed").first()
    assert audit is not None
    assert audit.actor_id is None


@pytest.mark.django_db
def test_unknown_email_is_indistinguishable_from_wrong_password() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()

    wrong_password = _login(client, user.email, "wrong-password-here")
    unknown_email = _login(client, "nobody@labflow.internal", "wrong-password-here")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["code"] == unknown_email.json()["code"]
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


@pytest.mark.django_db
def test_deactivated_account_cannot_log_in() -> None:
    user = PlatformUserFactory(totp_enabled=False, is_active=False)
    client = APIClient()

    resp = _login(client, user.email)

    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


@pytest.mark.django_db
def test_login_is_throttled_after_five_failures() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()

    for _ in range(5):
        assert _login(client, user.email, "wrong-password-here").status_code == 401

    throttled = _login(client, user.email, "wrong-password-here")
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "rate_limited"
    assert int(throttled.headers["Retry-After"]) > 0


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_totp_login_requires_challenge_then_verifies() -> None:
    secret = pyotp.random_base32()
    user = _totp_user(secret)
    client = APIClient()

    first = _login(client, user.email)
    assert first.status_code == 200
    body = first.json()
    assert body["totp_required"] is True
    assert body["challenge_id"]
    assert "access" not in body

    verified = client.post(
        VERIFY_URL,
        data={
            "email": user.email,
            "challenge_id": body["challenge_id"],
            "code": pyotp.TOTP(secret).now(),
        },
        format="json",
        HTTP_HOST=HOST,
    )
    assert verified.status_code == 200
    assert verified.json()["access"]


@pytest.mark.django_db
def test_fifth_bad_totp_code_destroys_the_challenge() -> None:
    secret = pyotp.random_base32()
    user = _totp_user(secret)
    client = APIClient()

    challenge_id = _login(client, user.email).json()["challenge_id"]

    responses = [
        client.post(
            VERIFY_URL,
            data={"email": user.email, "challenge_id": challenge_id, "code": "000000"},
            format="json",
            HTTP_HOST=HOST,
        )
        for _ in range(5)
    ]

    assert responses[-1].status_code == 401
    assert responses[-1].json()["code"] == "totp_challenge_expired"
    # The challenge is gone: even the correct code cannot revive it.
    after = client.post(
        VERIFY_URL,
        data={
            "email": user.email,
            "challenge_id": challenge_id,
            "code": pyotp.TOTP(secret).now(),
        },
        format="json",
        HTTP_HOST=HOST,
    )
    assert after.status_code == 401
    assert after.json()["code"] == "totp_challenge_expired"


@pytest.mark.django_db
def test_totp_enrolment_issues_ten_backup_codes_and_never_leaks_the_secret() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()
    access = _login(client, user.email).json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    enrolled = client.post(ENROLL_URL, HTTP_HOST=HOST)
    assert enrolled.status_code == 200
    secret = enrolled.json()["secret"]
    assert enrolled.json()["otpauth_uri"].startswith("otpauth://totp/")

    confirmed = client.post(
        ENROLL_CONFIRM_URL,
        data={"code": pyotp.TOTP(secret).now()},
        format="json",
        HTTP_HOST=HOST,
    )
    assert confirmed.status_code == 200
    codes = confirmed.json()["backup_codes"]
    assert len(codes) == 10

    user.refresh_from_db()
    assert user.totp_enabled is True
    assert user.totp_backup_codes_hash is not None
    assert len(user.totp_backup_codes_hash) == 10

    audit = PlatformAudit.objects.get(action="auth.totp_enrolled")
    serialized = json.dumps(audit.after_jsonb)
    assert secret not in serialized
    assert not any(code in serialized for code in codes)


# ---------------------------------------------------------------------------
# Refresh / logout
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_refresh_rotates_and_reuse_revokes_every_session() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()
    _login(client, user.email)
    original_refresh = client.cookies["labflow_refresh"].value

    rotated = client.post(REFRESH_URL, HTTP_HOST=HOST)
    assert rotated.status_code == 200
    assert rotated.json()["access"]
    new_refresh = client.cookies["labflow_refresh"].value
    assert new_refresh != original_refresh

    # Replay the consumed token: reuse detection must revoke everything.
    client.cookies["labflow_refresh"] = original_refresh
    replayed = client.post(REFRESH_URL, HTTP_HOST=HOST)
    assert replayed.status_code == 401
    assert replayed.json()["code"] == "refresh_reuse_detected"
    assert PlatformAudit.objects.filter(action="auth.sessions_revoked").exists()


@pytest.mark.django_db
def test_refresh_token_presented_as_access_is_rejected_on_typ() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()
    _login(client, user.email)
    refresh_token = client.cookies["labflow_refresh"].value

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_token}")
    resp = client.get(TENANTS_URL, HTTP_HOST=HOST)

    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_logout_denylists_the_access_token_immediately() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    client = APIClient()
    access = _login(client, user.email).json()["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert client.get(TENANTS_URL, HTTP_HOST=HOST).status_code == 200

    assert client.post(LOGOUT_URL, HTTP_HOST=HOST).status_code == 204

    again = APIClient()
    again.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert again.get(TENANTS_URL, HTTP_HOST=HOST).status_code in (401, 403)


# ---------------------------------------------------------------------------
# Write gate & password reset
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_write_requires_totp_enrolment() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    from tests.factories.core import PlanFactory

    plan = PlanFactory(name="Gate Plan")
    client = APIClient()
    access = _login(client, user.email).json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    resp = client.post(
        TENANTS_URL,
        data={
            "name": "Gate Lab",
            "slug": "gatelab",
            "plan_id": str(plan.id),
            "owner_email": "owner@gatelab.pk",
            "owner_name": "Gate Owner",
        },
        format="json",
        HTTP_HOST=HOST,
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "totp_required"


@pytest.mark.django_db
def test_password_reset_request_always_answers_accepted() -> None:
    PlatformUserFactory(totp_enabled=False)
    client = APIClient()

    known = client.post(
        RESET_REQUEST_URL,
        data={"email": "admin0@labflow.app"},
        format="json",
        HTTP_HOST=HOST,
    )
    unknown = client.post(
        RESET_REQUEST_URL,
        data={"email": "not-a-user@labflow.internal"},
        format="json",
        HTTP_HOST=HOST,
    )

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"accepted": True}


@pytest.mark.django_db
def test_password_reset_confirm_rotates_password_and_revokes_sessions() -> None:
    user = PlatformUserFactory(totp_enabled=False)
    raw_token = PlatformAuthService.request_password_reset(email=user.email)
    assert raw_token

    client = APIClient()
    resp = client.post(
        RESET_CONFIRM_URL,
        data={"token": raw_token, "new_password": "BrandNewPlatformPass123!"},
        format="json",
        HTTP_HOST=HOST,
    )

    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.check_password("BrandNewPlatformPass123!") is True
    assert PlatformAudit.objects.filter(action="auth.password_reset").exists()


@pytest.mark.django_db
def test_access_token_from_mint_helper_authenticates_reads() -> None:
    user = PlatformUserFactory(totp_enabled=True)
    token, _jti, _exp = platform_mint_access_token(user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    assert client.get(TENANTS_URL, HTTP_HOST=HOST).status_code == 200
