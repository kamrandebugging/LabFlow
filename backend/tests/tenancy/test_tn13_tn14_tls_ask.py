import logging
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from apps.core.models import Domain, Tenant
from apps.platform.tls import (
    get_hourly_miss_count,
    verify_tls_domain,
)


@pytest.fixture(autouse=True)
def clear_tls_cache() -> None:
    """Clear Django cache before each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client() -> Client:
    """Client configured for public schema routing (Doc 04 §6.4)."""
    return Client(HTTP_HOST="localhost")


def _create_test_tenant(slug: str, name: str, status: str) -> Tenant:
    """Create test tenant without running schema DDL for ultra-fast tests."""
    tenant = Tenant(
        schema_name=f"tenant_{slug}",
        slug=slug,
        name=name,
        status=status,
    )
    tenant.auto_create_schema = False
    tenant.save()
    Domain.objects.create(
        tenant=tenant,
        domain=f"{slug}.labflow.app",
        is_primary=True,
    )
    return tenant


@pytest.fixture
def active_tenant(db: None) -> Tenant:
    return _create_test_tenant("active-lab", "Active Lab", Tenant.Status.ACTIVE)


@pytest.fixture
def provisioning_tenant(db: None) -> Tenant:
    return _create_test_tenant(
        "prov-lab", "Provisioning Lab", Tenant.Status.PROVISIONING
    )


@pytest.fixture
def suspended_tenant(db: None) -> Tenant:
    return _create_test_tenant("susp-lab", "Suspended Lab", Tenant.Status.SUSPENDED)


@pytest.fixture
def deleted_tenant(db: None) -> Tenant:
    return _create_test_tenant("deleted-lab", "Deleted Lab", Tenant.Status.DELETED)


@pytest.mark.django_db
class TestTN13TLSAskEndpoint:
    """Doc 04 §6.4 & §15.3, TN-13: TLS ask logic and status verification."""

    def test_apex_labflow_app_returns_200_no_db_queries(self, client: Client) -> None:
        """Apex labflow.app is pre-approved; zero target DB queries."""
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/internal/tls-check?domain=labflow.app")
        assert response.status_code == 200
        assert response.content == b""
        target_queries = [q for q in queries if "labflow.app" in q["sql"]]
        assert len(target_queries) == 0

        with CaptureQueriesContext(connection) as direct_queries:
            assert verify_tls_domain("labflow.app") is True
        assert len(direct_queries) == 0

    def test_configured_platform_base_domain_apex_returns_200(
        self, client: Client
    ) -> None:
        """Configured settings.PLATFORM_BASE_DOMAIN apex is also pre-approved."""
        with override_settings(PLATFORM_BASE_DOMAIN="custom-platform.pk"):
            response = client.get("/internal/tls-check?domain=custom-platform.pk")
            assert response.status_code == 200
            assert response.content == b""

            with CaptureQueriesContext(connection) as direct_queries:
                assert verify_tls_domain("custom-platform.pk") is True
            assert len(direct_queries) == 0

    def test_active_tenant_domain_returns_200(
        self, client: Client, active_tenant: Tenant
    ) -> None:
        """Active tenant domain lookup returns 200 with empty body."""
        response = client.get("/internal/tls-check?domain=active-lab.labflow.app")
        assert response.status_code == 200
        assert response.content == b""

    def test_provisioning_tenant_domain_returns_200(
        self, client: Client, provisioning_tenant: Tenant
    ) -> None:
        """Provisioning tenant domain returns 200 during onboarding."""
        response = client.get("/internal/tls-check?domain=prov-lab.labflow.app")
        assert response.status_code == 200
        assert response.content == b""

    def test_suspended_tenant_domain_returns_200(
        self, client: Client, suspended_tenant: Tenant
    ) -> None:
        """Suspended tenant domain returns 200 (cert valid even if suspended)."""
        response = client.get("/internal/tls-check?domain=susp-lab.labflow.app")
        assert response.status_code == 200
        assert response.content == b""

    def test_deleted_tenant_domain_returns_404(
        self, client: Client, deleted_tenant: Tenant
    ) -> None:
        """Deleted tenant domain fails verification and returns 404."""
        response = client.get("/internal/tls-check?domain=deleted-lab.labflow.app")
        assert response.status_code == 404
        assert response.content == b""

    def test_unknown_host_returns_404(self, client: Client) -> None:
        """Unregistered single-label host returns 404."""
        response = client.get("/internal/tls-check?domain=unknown-lab.labflow.app")
        assert response.status_code == 404
        assert response.content == b""

    def test_two_labels_deep_subdomain_refused_without_db_lookup(
        self, client: Client, active_tenant: Tenant
    ) -> None:
        """Two labels deep is refused with 404 without target DB lookup."""
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/internal/tls-check?domain=deep.nested.labflow.app")
        assert response.status_code == 404
        assert response.content == b""
        target_queries = [
            q for q in queries if "deep" in q["sql"] or "nested" in q["sql"]
        ]
        assert len(target_queries) == 0

        with CaptureQueriesContext(connection) as direct_queries:
            assert verify_tls_domain("deep.nested.labflow.app") is False
        assert len(direct_queries) == 0

    def test_foreign_domain_refused_without_db_lookup(self, client: Client) -> None:
        """Foreign domain (e.g. attacker.com) is refused with 404."""
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/internal/tls-check?domain=attacker.com")
        assert response.status_code == 404
        assert response.content == b""
        target_queries = [q for q in queries if "attacker.com" in q["sql"]]
        assert len(target_queries) == 0

        with CaptureQueriesContext(connection) as direct_queries:
            assert verify_tls_domain("attacker.com") is False
        assert len(direct_queries) == 0

    def test_missing_or_empty_domain_parameter_returns_404(
        self, client: Client
    ) -> None:
        """Missing or empty ?domain= parameter returns 404."""
        assert client.get("/internal/tls-check").status_code == 404
        assert client.get("/internal/tls-check?domain=").status_code == 404
        assert client.get("/internal/tls-check?domain=   ").status_code == 404

    def test_case_insensitivity_and_trailing_dot(
        self, client: Client, active_tenant: Tenant
    ) -> None:
        """Domain matching is case-insensitive with optional trailing root dot."""
        response = client.get("/internal/tls-check?domain=ACTIVE-LAB.LABFLOW.APP")
        assert response.status_code == 200

        response_dot = client.get("/internal/tls-check?domain=active-lab.labflow.app.")
        assert response_dot.status_code == 200


@pytest.mark.django_db
class TestTN14NegativeCacheAndMissAlerts:
    """Doc 04 §6.4 & §17, TN-14: Negative caching and miss burst alerting."""

    def test_negative_cache_keeps_db_queries_flat(self, client: Client) -> None:
        """First miss queries DB; second miss hits cache with 0 target queries."""
        host = "scanner-probe-1.labflow.app"
        cache_key = f"platform:tls-ask:miss:{host}"
        assert cache.get(cache_key) is None

        # First request: misses DB, populates cache
        with CaptureQueriesContext(connection) as q1:
            resp1 = client.get(f"/internal/tls-check?domain={host}")
        assert resp1.status_code == 404
        target_queries_q1 = [q for q in q1 if host in q["sql"]]
        assert len(target_queries_q1) > 0
        assert cache.get(cache_key) is not None

        # Second request: served from negative cache, 0 target DB queries
        with CaptureQueriesContext(connection) as q2:
            resp2 = client.get(f"/internal/tls-check?domain={host}")
        assert resp2.status_code == 404
        target_queries_q2 = [q for q in q2 if host in q["sql"]]
        assert len(target_queries_q2) == 0

        # Direct check on verify_tls_domain: exactly 0 queries on cache hit
        with CaptureQueriesContext(connection) as direct_queries:
            assert verify_tls_domain(host) is False
        assert len(direct_queries) == 0

    def test_foreign_domain_repeated_probe_hits_negative_cache(
        self, client: Client
    ) -> None:
        """Repeated foreign domain query hits negative cache without increment."""
        foreign_host = "repeated-attacker.com"
        initial_misses = get_hourly_miss_count()

        resp1 = client.get(f"/internal/tls-check?domain={foreign_host}")
        assert resp1.status_code == 404
        assert get_hourly_miss_count() == initial_misses + 1
        assert cache.get(f"platform:tls-ask:miss:{foreign_host}") is not None

        # Second probe: hits negative cache immediately, count does not increment
        resp2 = client.get(f"/internal/tls-check?domain={foreign_host}")
        assert resp2.status_code == 404
        assert get_hourly_miss_count() == initial_misses + 1

    def test_cache_failure_degrades_gracefully_without_500(
        self, client: Client, active_tenant: Tenant
    ) -> None:
        """Redis cache failure degrades safely to DB/404 without raising 500."""
        with (
            patch("apps.platform.tls.cache.get", side_effect=Exception("Redis down")),
            patch("apps.platform.tls.cache.set", side_effect=Exception("Redis down")),
        ):
            # Valid tenant still returns 200
            resp_valid = client.get("/internal/tls-check?domain=active-lab.labflow.app")
            assert resp_valid.status_code == 200

            # Invalid domain returns 404 without 500
            resp_invalid = client.get(
                "/internal/tls-check?domain=unknown-fallback.labflow.app"
            )
            assert resp_invalid.status_code == 404

    def test_random_ask_hosts_all_404_and_burst_alert_fires(
        self, client: Client, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TN-14: multiple random ask hosts all return 404; alert fires."""
        caplog.set_level(logging.WARNING)

        with patch("apps.platform.tls.TLS_BURST_ALERT_THRESHOLD", 10):
            for i in range(15):
                host = f"random-scan-{i}.labflow.app"
                resp = client.get(f"/internal/tls-check?domain={host}")
                assert resp.status_code == 404

        alert_logs = [
            record
            for record in caplog.records
            if "tls_ask_miss_burst" in record.message
            or "TLS ask miss burst" in record.message
        ]
        assert len(alert_logs) > 0
