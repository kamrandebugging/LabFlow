"""LAB-24 (KAN-144): governance guard — the ranges API rejects backdated rows.

422 ``effective_from_in_past`` when ``effective_from`` is in the past.
Historical seeding bypasses the API via ``CatalogService`` directly (the
seed path); the service layer itself is unguarded.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role, StaffUser
from apps.catalog.models import Test
from apps.catalog.services import CatalogService
from apps.core.models import Tenant  # noqa: F401  (fixture type hints)
from tests.factories.staff_user import StaffUserFactory


@pytest.fixture
def gov_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
        return {
            "HTTP_AUTHORIZATION": f"Bearer {session['access']}",
            "HTTP_HOST": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def gov_owner(tenant_a: Any) -> Any:
    with tenant_context(tenant_a):
        return StaffUserFactory(
            role=Role.OWNER, branch=None, email="gov_owner@tenant.com"
        )


@pytest.fixture
def gov_test(tenant_a: Any) -> Test:
    with tenant_context(tenant_a):
        return Test.objects.create(
            code="GLU", name="Glucose", category="Biochemistry", unit="mg/dL"
        )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sex": "M",
        "age_min_days": 0,
        "age_max_days": 365,
        "low": "70.000",
        "high": "100.000",
        "critical_low": "40.000",
        "critical_high": "400.000",
        "unit": "mg/dL",
        "effective_from": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "effective_to": None,
    }
    payload.update(overrides)
    return payload


def _post(client: Client, test_id: Any, headers: Any, **overrides: Any) -> Any:
    return client.post(
        f"/api/v1/tests/{test_id}/ranges",
        data=_payload(**overrides),
        content_type="application/json",
        **headers,
    )


@pytest.mark.django_db
class TestEffectiveFromInPastGuard:
    def test_api_rejects_past_effective_from(
        self,
        client: Client,
        tenant_a: Any,
        gov_headers: Any,
        gov_owner: StaffUser,
        gov_test: Test,
    ) -> None:
        """KAN-144: backdated row via API -> 422 effective_from_in_past."""
        with tenant_context(tenant_a):
            headers = gov_headers(gov_owner, tenant_id=tenant_a.schema_name)
            past = (timezone.localdate() - timedelta(days=1)).isoformat()
            res = _post(client, gov_test.id, headers, effective_from=past)
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "effective_from_in_past"

    def test_api_accepts_today_effective_from(
        self,
        client: Client,
        tenant_a: Any,
        gov_headers: Any,
        gov_owner: StaffUser,
        gov_test: Test,
    ) -> None:
        with tenant_context(tenant_a):
            headers = gov_headers(gov_owner, tenant_id=tenant_a.schema_name)
            today = timezone.localdate().isoformat()
            res = _post(client, gov_test.id, headers, effective_from=today)
            assert res.status_code == 201

    def test_api_accepts_future_effective_from(
        self,
        client: Client,
        tenant_a: Any,
        gov_headers: Any,
        gov_owner: StaffUser,
        gov_test: Test,
    ) -> None:
        with tenant_context(tenant_a):
            headers = gov_headers(gov_owner, tenant_id=tenant_a.schema_name)
            res = _post(client, gov_test.id, headers)
            assert res.status_code == 201

    def test_service_seed_path_allows_past(
        self, tenant_a: Any, gov_owner: StaffUser, gov_test: Test
    ) -> None:
        """Seed path (service layer) is exempt from the guard."""
        with tenant_context(tenant_a):
            row = CatalogService.create_reference_range(
                test_id=gov_test.id,
                sex="M",
                age_min_days=0,
                age_max_days=365,
                low=Decimal("70.000"),
                high=Decimal("100.000"),
                critical_low=Decimal("40.000"),
                critical_high=Decimal("400.000"),
                unit="mg/dL",
                effective_from=timezone.localdate() - timedelta(days=365),
                effective_to=None,
                actor=gov_owner,
            )
            assert row.id is not None
