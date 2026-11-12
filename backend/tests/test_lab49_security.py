"""LAB-49 security regression suite (OWASP API Top 10 program).

Each test is a negative test first (the attack fails), then the legitimate path
is covered by the existing feature suites. Runs against the real PostgreSQL and
Redis services like every other tenancy test.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import jwt
import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, override_settings
from django_tenants.utils import schema_context

from apps.accounts.auth_service import AuthService
from apps.accounts.jwt_engine import JWT_ALGORITHM, mint_refresh_token
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.core.authorization import ROLE_POLICY, normalize_url_name
from apps.core.management.commands.api_inventory import build_inventory
from tests.factories.staff_user import StaffUserFactory


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _auth_header(user: StaffUser, tenant_id: str = "tenant_a") -> str:
    with schema_context(tenant_id):
        session = AuthService.create_session(user, tenant_id=tenant_id)
    return f"Bearer {session['access']}"


def _client() -> Client:
    return Client(HTTP_HOST="tenant-a.localhost")


class TestSecretFailClosed:
    def test_required_secret_refuses_missing_value(self) -> None:
        from django.core.exceptions import ImproperlyConfigured

        import config.settings.base as base

        original = base._IS_LOCAL_DEV
        base._IS_LOCAL_DEV = False
        try:
            with pytest.raises(ImproperlyConfigured):
                base._require_env_secret("LABFLOW_TEST_ABSENT_SECRET")
        finally:
            base._IS_LOCAL_DEV = original

    def test_committed_totp_key_is_rejected_outside_dev(
        self, monkeypatch: Any
    ) -> None:
        from django.core.exceptions import ImproperlyConfigured

        import config.settings.base as base

        monkeypatch.setattr(base, "_IS_LOCAL_DEV", False)
        monkeypatch.setenv("DJANGO_SECRET_KEY", base._COMMITTED_TOTP_KEY)
        with pytest.raises(ImproperlyConfigured):
            base._require_env_secret(
                "DJANGO_SECRET_KEY",
                forbidden=base._PUBLIC_EXAMPLE_VALUES,
            )


class TestTotpHardening:
    def test_debug_master_code_never_verifies(self, tenant_a: Any) -> None:
        with schema_context(tenant_a.schema_name):
            user = StaffUserFactory(role=Role.OWNER, branch=None)
        challenge = AuthService.create_totp_challenge(
            str(user.id), tenant_id=tenant_a.schema_name
        )
        with override_settings(DEBUG=True):
            success, payload, err = AuthService.verify_totp_challenge(
                challenge_token=challenge,
                code="123456",
                tenant_id=tenant_a.schema_name,
            )
        assert success is False
        assert payload is None
        assert err in {"invalid_credentials", "totp_challenge_expired"}


class TestRolePolicy:
    def test_technician_cannot_call_owner_export(self, tenant_a: Any) -> None:
        with schema_context(tenant_a.schema_name):
            technician = StaffUserFactory(role=Role.TECHNICIAN)
            before = AuditLog.objects.filter(action="auth.access_denied").count()
        response = _client().post(
            "/api/v1/exports",
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION=_auth_header(cast(StaffUser, technician)),
            HTTP_IDEMPOTENCY_KEY="denied-1",
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
        with schema_context(tenant_a.schema_name):
            after = AuditLog.objects.filter(action="auth.access_denied").count()
        assert after == before + 1

    def test_every_authenticated_tenant_route_has_a_policy(self) -> None:
        missing: list[str] = []
        for route in build_inventory()["routes"]:
            if route["urlconf"] != "tenant" or route["public"]:
                continue
            if "IsAuthenticated" not in route["permissions"]:
                continue
            policy = ROLE_POLICY.get(normalize_url_name(route["name"]))
            if not policy:
                missing.append(f"{route['methods']} {route['path']}")
                continue
            for method in route["methods"]:
                if method not in policy:
                    missing.append(f"{method} {route['path']}")
        assert not missing, f"Routes with no role policy: {missing}"


class TestJwtClaims:
    def test_wrong_audience_is_rejected(self) -> None:
        from apps.accounts.jwt_engine import decode_jwt

        token = jwt.encode(
            {
                "sub": "00000000-0000-0000-0000-000000000001",
                "tenant": "tenant_a",
                "jti": "jti-1",
                "iat": 1,
                "exp": 9999999999,
                "typ": "access",
                "iss": "labflow",
                "aud": "someone-else",
            },
            settings.JWT_SIGNING_KEY,
            algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(ValueError):
            decode_jwt(token)

    def test_missing_issuer_is_rejected(self) -> None:
        from apps.accounts.jwt_engine import decode_jwt

        token = jwt.encode(
            {
                "sub": "00000000-0000-0000-0000-000000000001",
                "tenant": "tenant_a",
                "jti": "jti-2",
                "iat": 1,
                "exp": 9999999999,
                "typ": "access",
                "aud": "labflow-api",
            },
            settings.JWT_SIGNING_KEY,
            algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(ValueError):
            decode_jwt(token)

    def test_refresh_token_carries_iss_and_aud(self) -> None:
        token, _jti, _exp = mint_refresh_token(
            staff_user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            tenant_slug="tenant_a",
            family_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        )
        payload = jwt.decode(
            token,
            settings.JWT_SIGNING_KEY,
            algorithms=[JWT_ALGORITHM],
            audience="labflow-api",
        )
        assert payload["iss"] == "labflow"
        assert payload["aud"] == "labflow-api"


class TestRequestGuards:
    def test_oversize_body_is_413(self) -> None:
        with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=128):
            response = _client().post(
                "/api/v1/auth/login",
                data="{" + "x" * 512 + "}",
                content_type="application/json",
            )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"

    def test_security_headers_are_present(self) -> None:
        response = Client(HTTP_HOST="localhost").get("/healthz")
        assert response.status_code == 200
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy-Report-Only" in response
        assert "Permissions-Policy" in response

    def test_api_responses_are_not_cacheable(self, tenant_a: Any) -> None:
        response = _client().get("/api/v1/auth/tenant")
        assert "no-store" in response.get("Cache-Control", "")

    def test_api_docs_are_disabled_by_default(self) -> None:
        assert _client().get("/api/schema/").status_code == 404
        assert _client().get("/api/docs/").status_code == 404

    def test_cross_site_origin_on_login_is_refused(self, tenant_a: Any) -> None:
        response = Client(
            HTTP_HOST="tenant-a.localhost", HTTP_ORIGIN="https://evil.example"
        ).post(
            "/api/v1/auth/login",
            data='{"email":"a@b.com","password":"whatever"}',
            content_type="application/json",
        )
        assert response.status_code == 403


class TestSafeFetch:
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:6379/",
            "http://127.0.0.1:8000/admin/",
            "http://10.0.0.5/hook",
            "http://192.168.1.10/hook",
            "file:///etc/passwd",
            "gopher://example.com/",
        ],
    )
    def test_unsafe_destinations_are_rejected(self, url: str) -> None:
        from apps.core.safe_fetch import UnsafeURLError, validate_url

        with (
            override_settings(ALLOW_INSECURE_LOCAL_WEBHOOKS=False),
            pytest.raises(UnsafeURLError),
        ):
            validate_url(url)

    def test_public_https_destination_is_allowed(self, monkeypatch: Any) -> None:
        from apps.core.safe_fetch import validate_url

        def fake_getaddrinfo(*args: Any, **kwargs: Any) -> list[Any]:
            return [(2, 1, 6, "", ("93.184.216.34", 443))]

        monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
        assert validate_url("https://n8n.example.com/hook")


class TestPdfBoundary:
    """API7/API10: PDF rendering must not fetch external URLs."""

    def test_pdf_templates_contain_no_external_urls(self) -> None:
        from pathlib import Path

        backend = Path(settings.BASE_DIR)
        templates = [
            backend / "apps/reports/pdf/templates/report.html",
            backend / "apps/partners/templates/statement.html",
        ]
        for template in templates:
            text = template.read_text(encoding="utf-8")
            assert "http://" not in text
            assert "https://" not in text
            # No remote image/script/link source; the QR uses a data: URI.
            assert 'src="http' not in text
            assert "src='http" not in text


class TestConsumptionAllowlists:
    def test_whatsapp_url_must_be_wa_me_https(self) -> None:
        from apps.automation.services import CallbackError, _validate_whatsapp_url

        _validate_whatsapp_url("https://wa.me/923001234567")
        for bad in (
            "http://wa.me/923001234567",
            "https://evil.example/923001234567",
            "javascript:alert(1)",
        ):
            with pytest.raises(CallbackError):
                _validate_whatsapp_url(bad)


class TestPasswordResetDelivery:
    def test_reset_request_delivers_one_single_use_link(self, tenant_a: Any) -> None:
        from django.core import mail

        mail.outbox = []
        with schema_context(tenant_a.schema_name):
            StaffUserFactory(role=Role.RECEPTION, email="reset-me@labflow.app")
        response = _client().post(
            "/api/v1/auth/password-reset/request",
            data='{"email":"reset-me@labflow.app"}',
            content_type="application/json",
        )
        assert response.status_code == 202
        assert len(mail.outbox) == 1
        assert "token=" in mail.outbox[0].body


class TestReviewFixups:
    def test_published_example_secret_is_rejected_outside_dev(
        self, monkeypatch: Any
    ) -> None:
        from django.core.exceptions import ImproperlyConfigured

        import config.settings.base as base

        monkeypatch.setattr(base, "_IS_LOCAL_DEV", False)
        monkeypatch.setenv("DJANGO_SECRET_KEY", base._COMMITTED_TOTP_KEY)
        with pytest.raises(ImproperlyConfigured):
            base._require_env_secret(
                "DJANGO_SECRET_KEY", forbidden=base._PUBLIC_EXAMPLE_VALUES
            )

    def test_refresh_with_omitted_user_agent_is_rejected(self, tenant_a: Any) -> None:
        with schema_context(tenant_a.schema_name):
            user = StaffUserFactory(role=Role.RECEPTION)
        session = AuthService.create_session(
            user=cast(StaffUser, user),
            tenant_id=tenant_a.schema_name,
            ip="203.0.113.9",
            user_agent="UA-original",
        )
        success, payload, err = AuthService.refresh_tokens(
            session["refresh_token"], ip="203.0.113.9", user_agent=""
        )
        assert success is False
        assert payload is None
        assert err == "refresh_fingerprint_mismatch"

    def test_chunked_body_without_content_length_is_413(self) -> None:
        from types import SimpleNamespace

        from apps.core.middleware import PayloadLimitMiddleware

        request = SimpleNamespace(
            META={"HTTP_TRANSFER_ENCODING": "chunked"},
            content_length=None,
            method="POST",
        )
        with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1024):
            response = PayloadLimitMiddleware(lambda _request: None)(request)
        assert response.status_code == 413
        import json

        assert json.loads(response.content)["error"]["code"] == "payload_too_large"

    def test_inventory_does_not_claim_admin_ip_gating(self) -> None:
        surfaces = build_inventory()["gated_surfaces"]
        admin_note = next(s for s in surfaces if s["path"] == "/admin/")["note"]
        assert "NOT enabled by default" in admin_note

    def test_every_public_url_name_resolves(self) -> None:
        from apps.core.authorization import PUBLIC_URL_NAMES

        names = {route["name"] for route in build_inventory()["routes"]}
        names.update({"public-healthz", "public-readyz"})
        assert not (PUBLIC_URL_NAMES - names)
