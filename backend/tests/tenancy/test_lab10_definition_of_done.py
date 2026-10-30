import pytest
from django.core.cache import cache
from django.test import Client

from apps.core.models import Domain, Tenant
from apps.platform.tls import get_hourly_miss_count


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client() -> Client:
    """Client configured for public schema routing (Doc 04 §6.4)."""
    return Client(HTTP_HOST="localhost")


def _create_fast_tenant(slug: str, name: str, status: str) -> Tenant:
    """Create test tenant without running schema migrations."""
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


@pytest.mark.django_db
class TestLAB10DefinitionOfDone:
    """LAB-10 DoD Verification:

    DoD: Fresh demo tenant host issues on first visit; unknown hosts refused.
    """

    def test_dod_fresh_tenant_host_issues_on_first_visit(self, client: Client) -> None:
        """Fresh tenant in provisioning or active status is approved immediately."""
        _create_fast_tenant("demo", "Demo Clinic", Tenant.Status.PROVISIONING)

        response = client.get("/internal/tls-check?domain=demo.labflow.app")
        assert response.status_code == 200
        assert response.content == b""

    def test_dod_unknown_hosts_refused(self, client: Client) -> None:
        """Unknown hosts are refused with 404 and cached in negative cache."""
        unknown_host = "fake-tenant.labflow.app"
        response = client.get(f"/internal/tls-check?domain={unknown_host}")
        assert response.status_code == 404
        assert response.content == b""
        assert cache.get(f"platform:tls-ask:miss:{unknown_host}") is not None

    def test_dod_all_authorized_lifecycle_states(self, client: Client) -> None:
        """Provisioning, active, and suspended tenants approved; deleted refused."""
        states = [
            (Tenant.Status.PROVISIONING, True),
            (Tenant.Status.ACTIVE, True),
            (Tenant.Status.SUSPENDED, True),
            (Tenant.Status.DELETED, False),
        ]
        for status, should_pass in states:
            slug = f"state-{status}"
            _create_fast_tenant(slug, f"State {status}", status)
            resp = client.get(f"/internal/tls-check?domain={slug}.labflow.app")
            assert resp.status_code == (200 if should_pass else 404)

    def test_dod_negative_cache_and_hourly_miss_tracking(self, client: Client) -> None:
        """Hourly miss counter increments on misses."""
        host = "scanner-test-99.labflow.app"
        initial_count = get_hourly_miss_count()
        resp = client.get(f"/internal/tls-check?domain={host}")
        assert resp.status_code == 404
        assert get_hourly_miss_count() == initial_count + 1
