"""Public staff "forgot password" request endpoint (Gaps 1 + 2).

Covers:
- existing email stores exactly one pending request, unknown email stores none
- both always answer 202 {"accepted": true} (no enumeration)
- 3/hour per email, 5/15 minutes per IP, 429 + Retry-After
- Redis outage fails closed with 429
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, StaffPasswordResetRequest, StaffUser
from tests.factories.branch import BranchFactory
from tests.factories.staff_user import StaffUserFactory

URL = "/api/v1/auth/password-reset/staff-request"


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def branch(tenant_a: Any) -> Any:
    with tenant_context(tenant_a):
        return BranchFactory(code="PR1", name="Password Request Branch")


@pytest.fixture
def reception(tenant_a: Any, branch: Any) -> StaffUser:
    with tenant_context(tenant_a):
        return cast(
            StaffUser,
            StaffUserFactory(
                role=Role.RECEPTION,
                branch=branch,
                email="requester@staffrequest.test",
                display_name="Requester",
            ),
        )


def _post(
    email: str,
    *,
    ip: str = "10.10.0.1",
    host: str = "tenant-a.localhost",
) -> Any:
    return APIClient().post(
        URL,
        data={"email": email, "display_name": "Requester"},
        format="json",
        HTTP_HOST=host,
        REMOTE_ADDR=ip,
    )


@pytest.mark.django_db
@pytest.mark.tenancy
class TestStaffPasswordRequest:
    def test_existing_email_stores_one_pending_request(
        self, tenant_a: Any, reception: StaffUser
    ) -> None:
        response = _post(reception.email)
        assert response.status_code == 202
        assert response.json() == {"accepted": True}

        with tenant_context(tenant_a):
            rows = StaffPasswordResetRequest.objects.filter(
                email__iexact=reception.email
            )
            assert rows.count() == 1
            row = rows.first()
            assert row is not None
            assert row.status == StaffPasswordResetRequest.Status.PENDING

    def test_unknown_email_is_accepted_but_not_stored(
        self, tenant_a: Any, reception: StaffUser
    ) -> None:
        response = _post("nobody@staffrequest.test")
        assert response.status_code == 202
        assert response.json() == {"accepted": True}

        with tenant_context(tenant_a):
            assert not StaffPasswordResetRequest.objects.filter(
                email="nobody@staffrequest.test"
            ).exists()

    def test_third_request_limit_per_email_returns_429_with_retry_after(
        self, reception: StaffUser
    ) -> None:
        for _ in range(3):
            assert _post(reception.email).status_code == 202

        limited = _post(reception.email)
        assert limited.status_code == 429
        retry_after = int(limited["Retry-After"])
        assert 0 < retry_after <= 3600

    def test_fifth_request_limit_per_ip_returns_429_for_distinct_emails(
        self, tenant_a: Any
    ) -> None:
        # Distinct emails keep the per-email counter at 1 each; the sixth
        # request from the same IP must trip the 5/15-minute IP window.
        for index in range(5):
            response = _post(f"user{index}@staffrequest.test", ip="10.10.0.2")
            assert response.status_code == 202, response.content

        limited = _post("user5@staffrequest.test", ip="10.10.0.2")
        assert limited.status_code == 429
        assert 0 < int(limited["Retry-After"]) <= 900

        # A different IP is unaffected by the first IP's window.
        assert _post("user6@staffrequest.test", ip="10.10.0.3").status_code == 202

    def test_redis_outage_fails_closed(self, reception: StaffUser) -> None:
        with patch(
            "apps.accounts.throttling.cache.incr",
            side_effect=Exception("redis down"),
        ):
            response = _post(reception.email)

        assert response.status_code == 429
        assert response["Retry-After"]
