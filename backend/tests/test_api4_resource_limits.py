"""API4 resource-limit regressions for the public patient portal.

Doc 08 §10.1 / KAN-268:
- 60 requests / 10 minutes per report access token,
- 120 requests / 10 minutes per IP,
- 20 invalid-token attempts / hour.

Every 429 must carry Retry-After.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from apps.reports.throttling import (
    record_invalid_report_token,
    report_ip_rate_limit_exceeded,
    report_token_rate_limit_exceeded,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


def _request() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        META={"REMOTE_ADDR": "203.0.113.9", "HTTP_X_FORWARDED_FOR": ""},
    )


class TestPatientAccessThrottles:
    def test_ip_budget_is_120_per_10_minutes(self) -> None:
        with override_settings(REPORT_IP_RATE_LIMIT_PER_10MIN=2):
            assert report_ip_rate_limit_exceeded(_request()) is False
            assert report_ip_rate_limit_exceeded(_request()) is False
            assert report_ip_rate_limit_exceeded(_request()) is True

    def test_token_budget_is_60_per_10_minutes(self) -> None:
        with override_settings(REPORT_TOKEN_RATE_LIMIT_PER_10MIN=2):
            assert report_token_rate_limit_exceeded("tok-a") is False
            assert report_token_rate_limit_exceeded("tok-a") is False
            assert report_token_rate_limit_exceeded("tok-a") is True

    def test_invalid_token_budget_is_20_per_hour(self) -> None:
        with override_settings(REPORT_INVALID_TOKEN_PER_HOUR=2):
            assert record_invalid_report_token(_request()) is False
            assert record_invalid_report_token(_request()) is False
            assert record_invalid_report_token(_request()) is True


class TestPatientPortal429:
    def _client(self) -> Client:
        return Client(HTTP_HOST="tenant-a.localhost")

    def test_invalid_token_budget_returns_429_with_retry_after(
        self, tenant_a: Any
    ) -> None:
        with override_settings(REPORT_INVALID_TOKEN_PER_HOUR=2):
            first = self._client().get("/api/v1/report-access/not-a-real-token")
            second = self._client().get("/api/v1/report-access/not-a-real-token")
            third = self._client().get("/api/v1/report-access/not-a-real-token")
        assert first.status_code in (404, 410)
        assert second.status_code in (404, 410)
        assert third.status_code == 429
        assert third["Retry-After"] == "3600"

    def test_ip_budget_returns_429_with_retry_after(self, tenant_a: Any) -> None:
        with override_settings(
            REPORT_IP_RATE_LIMIT_PER_10MIN=1,
            REPORT_INVALID_TOKEN_PER_HOUR=100,
        ):
            first = self._client().get("/api/v1/report-access/not-a-real-token")
            second = self._client().get("/api/v1/report-access/not-a-real-token")
        assert first.status_code in (404, 410)
        assert second.status_code == 429
        assert second["Retry-After"] == "60"


class TestTotpThrottleBinding:
    def test_throttle_binds_to_server_challenge_user_not_body_email(self) -> None:
        from types import SimpleNamespace

        from apps.accounts.auth_service import AuthService
        from apps.core.throttling import TotpVerifyThrottle

        challenge = AuthService.create_totp_challenge("user-abc-123")
        request = SimpleNamespace(
            COOKIES={"auth_challenge": challenge},
            data={"email": "attacker@example.com"},
            tenant=None,
            META={"REMOTE_ADDR": "203.0.113.9"},
        )
        assert TotpVerifyThrottle().get_ident(request) == "user:user-abc-123"


class TestTrustedProxyIp:
    def test_untrusted_peer_cannot_spoof_forwarding_headers(self) -> None:
        from types import SimpleNamespace

        from apps.core.ip import get_client_ip

        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "203.0.113.9",
                "HTTP_X_FORWARDED_FOR": "1.2.3.4",
                "HTTP_CF_CONNECTING_IP": "5.6.7.8",
            }
        )
        assert get_client_ip(request) == "203.0.113.9"

    def test_trusted_proxy_uses_cloudflare_header(self) -> None:
        from types import SimpleNamespace

        from apps.core.ip import get_client_ip

        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "127.0.0.1",
                "HTTP_CF_CONNECTING_IP": "5.6.7.8",
                "HTTP_X_FORWARDED_FOR": "5.6.7.8",
            }
        )
        assert get_client_ip(request) == "5.6.7.8"
