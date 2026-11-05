"""Integration tests for reports and exceptions endpoints (Doc 03 §5.6, §6.1, §6.7).

Covers:
- GET /api/v1/reports — staff list with cursor pagination and filters.
- GET /api/v1/reports/<id> — staff detail with versions, deliveries, token state.
- GET /api/v1/exceptions — staff exceptions derived from real model states.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, StaffBranch, StaffUser
from apps.core.models import Subscription, Tenant
from apps.reports.models import (
    Report,
    ReportDelivery,
)
from apps.results.models import Result
from apps.samples.models import Sample, SampleTransfer
from tests.factories.accounts import StaffUserFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.core import PlanFactory
from tests.factories.patients import PatientContactFactory, PatientFactory
from tests.factories.reports import (
    ReportAccessTokenFactory,
    ReportDeliveryFactory,
    ReportFactory,
    ReportVersionFactory,
)
from tests.factories.results import ResultFactory
from tests.factories.samples import (
    SampleFactory,
    SampleTestFactory,
    SampleTransferFactory,
)


def _mint_jwt(staff_id: uuid.UUID, tenant_slug: str, role: str) -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    now = int(timezone.now().timestamp())
    payload = {
        "sub": str(staff_id),
        "tenant": tenant_slug,
        "role": role,
        "typ": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + 3600,
    }
    return str(jwt.encode(payload, str(signing_key), algorithm="HS256"))


def _authenticate_client(
    client: APIClient, staff: StaffUser, tenant: Tenant, role: str = "owner"
) -> None:
    token = _mint_jwt(staff.id, tenant.slug, role)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@pytest.fixture
def api_client(tenant_a: Tenant) -> APIClient:
    client = APIClient()
    client.defaults["HTTP_HOST"] = "tenant-a.localhost"
    return client


@pytest.fixture
def active_sub(tenant_a: Tenant) -> Subscription:
    plan = PlanFactory(name="ReportTestPlan", price=Decimal("150.00"))
    with schema_context("public"):
        sub, _ = Subscription.objects.update_or_create(
            tenant=tenant_a,
            defaults={
                "plan": plan,
                "status": Subscription.Status.ACTIVE,
                "starts_at": timezone.now() - timedelta(days=10),
            },
        )
    return sub


@pytest.mark.django_db
class TestReportsListEndpoint:
    """Tests for GET /api/v1/reports."""

    def test_unauthenticated_returns_401(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/reports")
        assert response.status_code == 401

    def test_empty_list_returns_200(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

        response = api_client.get("/api/v1/reports")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["results"] == []
        assert data["next_cursor"] is None

    def test_list_with_reports_and_cursor_pagination(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory(name="Branch North")
            staff = StaffUserFactory(role=Role.OWNER, branch=branch)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            # Create 3 reports with distinct samples
            reports = []
            for _i in range(3):
                sample = SampleFactory(branch=branch)
                rpt = ReportFactory(
                    sample=sample,
                    status=Report.Status.FINAL,
                    current_version=1,
                )
                reports.append(rpt)

        # Page with limit 2
        response = api_client.get("/api/v1/reports?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert data["next_cursor"] is not None

        # Fetch next page using cursor
        cursor = data["next_cursor"]
        response2 = api_client.get(f"/api/v1/reports?cursor={cursor}&limit=2")
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["results"]) == 1
        assert data2["next_cursor"] is None

    def test_filter_by_status(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory()
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            sample1 = SampleFactory(branch=branch)
            ReportFactory(sample=sample1, status=Report.Status.DRAFT)
            sample2 = SampleFactory(branch=branch)
            ReportFactory(sample=sample2, status=Report.Status.FINAL)

        # Filter valid status
        res = api_client.get("/api/v1/reports?status=final")
        assert res.status_code == 200
        assert len(res.json()["results"]) == 1
        assert res.json()["results"][0]["status"] == "final"

        # Invalid status returns 422 Problem+JSON
        res_invalid = api_client.get("/api/v1/reports?status=unknown_status")
        assert res_invalid.status_code == 422
        assert res_invalid["Content-Type"] == "application/problem+json"
        assert res_invalid.json()["code"] == "validation_error"

    def test_filter_by_branch(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            b2 = BranchFactory(name="B2")
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            ReportFactory(sample=SampleFactory(branch=b1))
            ReportFactory(sample=SampleFactory(branch=b2))

        res = api_client.get(f"/api/v1/reports?branch={b1.id}")
        assert res.status_code == 200
        assert len(res.json()["results"]) == 1
        assert res.json()["results"][0]["branch_id"] == str(b1.id)

    def test_filter_by_patient_search(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory()
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            p1 = PatientFactory(name="Fatima Zahra", mrn="MRN-FATIMA-001")
            s1 = SampleFactory(branch=branch, invoice__patient=p1)
            ReportFactory(sample=s1)

            p2 = PatientFactory(name="Ali Khan", mrn="MRN-ALI-002")
            s2 = SampleFactory(branch=branch, invoice__patient=p2)
            ReportFactory(sample=s2)

        res = api_client.get("/api/v1/reports?patient=Fatima")
        assert res.status_code == 200
        assert len(res.json()["results"]) == 1
        assert res.json()["results"][0]["patient_name"] == "Fatima Zahra"

    def test_validation_edge_cases_422(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

        # Invalid limit < 1
        res = api_client.get("/api/v1/reports?limit=0")
        assert res.status_code == 422
        assert res["Content-Type"] == "application/problem+json"

        # Invalid limit > 100
        res = api_client.get("/api/v1/reports?limit=500")
        assert res.status_code == 422

        # Invalid branch UUID
        res = api_client.get("/api/v1/reports?branch=not-a-uuid")
        assert res.status_code == 422
        assert res.json()["code"] == "validation_error"

        # Invalid status filter
        res = api_client.get("/api/v1/reports?status=unknown_bogus_status")
        assert res.status_code == 422
        assert res.json()["code"] == "validation_error"

        # Corrupted cursor
        res = api_client.get("/api/v1/reports?cursor=not-valid-base64-json")
        assert res.status_code == 422
        assert res.json()["code"] == "validation_error"

    def test_unauthorized_role_returns_403(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            staff = StaffUserFactory(role="external_courier", branch=None)
            _authenticate_client(api_client, staff, tenant_a, "external_courier")

        res = api_client.get("/api/v1/reports")
        assert res.status_code == 403
        assert res["Content-Type"] == "application/problem+json"
        assert res.json()["code"] == "forbidden"

    def test_technician_branch_scoping_on_reports_list_and_detail(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="Assigned Branch")
            b2 = BranchFactory(name="Unassigned Branch")

            s1 = SampleFactory(branch=b1)
            r1 = ReportFactory(sample=s1, status=Report.Status.FINAL)

            s2 = SampleFactory(branch=b2)
            r2 = ReportFactory(sample=s2, status=Report.Status.FINAL)

            tech = StaffUserFactory(role=Role.TECHNICIAN, branch=b1)
            StaffBranch.objects.create(staff_user=tech, branch=b1, is_primary=True)

            _authenticate_client(api_client, tech, tenant_a, Role.TECHNICIAN)

        list_res = api_client.get("/api/v1/reports")
        assert list_res.status_code == 200
        ids = [item["id"] for item in list_res.json()["results"]]
        assert str(r1.id) in ids
        assert str(r2.id) not in ids

        d1 = api_client.get(f"/api/v1/reports/{r1.id}")
        assert d1.status_code == 200

        d2 = api_client.get(f"/api/v1/reports/{r2.id}")
        assert d2.status_code == 404

    def test_cross_tenant_isolation(
        self, tenant_a: Tenant, tenant_b: Tenant, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            b_a = BranchFactory(name="Branch A")
            s_a = SampleFactory(branch=b_a)
            r_a = ReportFactory(sample=s_a, status=Report.Status.FINAL)
            report_a_id = str(r_a.id)

        with tenant_context(tenant_b):
            b_b = BranchFactory(name="Branch B")
            s_b = SampleFactory(branch=b_b)
            r_b = ReportFactory(sample=s_b, status=Report.Status.FINAL)
            staff_b = StaffUserFactory(role=Role.OWNER, branch=None)

            client_b = APIClient()
            client_b.defaults["HTTP_HOST"] = "tenant-b.localhost"
            _authenticate_client(client_b, staff_b, tenant_b, Role.OWNER)

            list_res = client_b.get("/api/v1/reports")
            assert list_res.status_code == 200
            ids = [item["id"] for item in list_res.json()["results"]]
            assert str(r_b.id) in ids
            assert report_a_id not in ids

            detail_res = client_b.get(f"/api/v1/reports/{report_a_id}")
            assert detail_res.status_code == 404


@pytest.mark.django_db
class TestReportDetailEndpoint:
    """Tests for GET /api/v1/reports/<uuid:report_id>."""

    def test_unauthenticated_returns_401(self, api_client: APIClient) -> None:
        uid = uuid.uuid4()
        response = api_client.get(f"/api/v1/reports/{uid}")
        assert response.status_code == 401

    def test_nonexistent_returns_404_problem_json(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

        uid = uuid.uuid4()
        response = api_client.get(f"/api/v1/reports/{uid}")
        assert response.status_code == 404
        assert response["Content-Type"] == "application/problem+json"
        assert response.json()["code"] == "report_not_found"

    def test_detail_returns_report_with_versions_deliveries_and_token_state(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory(name="Gulberg")
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            patient = PatientFactory(name="Muhammad Imran", mrn="MRN-2026-00417")
            contact = PatientContactFactory(patient=patient, value="m.imran@email.com")
            sample = SampleFactory(branch=branch, invoice__patient=patient)
            test = TestFactory(name="Potassium (K+)", code="K+")
            SampleTestFactory(sample=sample, test=test)
            ResultFactory(
                sample=sample,
                test=test,
                value="4.5",
                unit="mmol/L",
                status=Result.Status.APPROVED,
            )

            report = ReportFactory(
                sample=sample,
                status=Report.Status.FINAL,
                current_version=1,
            )
            v1 = ReportVersionFactory(report=report, version=1, generated_by=staff)
            delivery = ReportDeliveryFactory(
                report=report,
                contact=contact,
                channel=ReportDelivery.Channel.EMAIL,
                status=ReportDelivery.Status.SENT,
            )
            token_row = ReportAccessTokenFactory(
                report=report,
                revoked_at=None,
            )

        response = api_client.get(f"/api/v1/reports/{report.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(report.id)
        assert data["status"] == "final"
        assert data["current_version"] == 1
        assert data["patient"]["full_name"] == "Muhammad Imran"
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version"] == 1
        assert data["versions"][0]["id"] == str(v1.id)
        assert len(data["deliveries"]) == 1
        assert data["deliveries"][0]["channel"] == "email"
        assert data["deliveries"][0]["id"] == str(delivery.id)
        assert len(data["access_tokens"]) == 1
        assert data["access_tokens"][0]["id"] == str(token_row.id)
        # Confidentiality: plain token and argon2 token_hash MUST NEVER be exposed!
        assert "token" not in data["access_tokens"][0]
        assert "token_hash" not in data["access_tokens"][0]
        assert data["access_tokens"][0]["is_active"] is True


@pytest.mark.django_db
class TestExceptionsEndpoint:
    """Tests for GET /api/v1/exceptions."""

    def test_unauthenticated_returns_401(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/exceptions")
        assert response.status_code == 401

    def test_honest_empty_state_when_zero_exceptions(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

        response = api_client.get("/api/v1/exceptions")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["counts"]["total"] == 0

    def test_exceptions_derived_from_real_model_data(
        self, tenant_a: Tenant, api_client: APIClient, active_sub: Subscription
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="Main Lab")
            b2 = BranchFactory(name="Satellite")
            staff = StaffUserFactory(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            # 1. Failed generation report
            s1 = SampleFactory(branch=b1)
            ReportFactory(
                sample=s1,
                generation_status=Report.GenerationStatus.FAILED,
                generation_error="Weasyprint render timeout",
            )

            # 2. Failed delivery
            s2 = SampleFactory(branch=b1)
            r2 = ReportFactory(sample=s2, status=Report.Status.FINAL)
            contact = PatientContactFactory(patient=s2.invoice.patient)
            ReportDeliveryFactory(
                report=r2,
                contact=contact,
                channel=ReportDelivery.Channel.WHATSAPP,
                status=ReportDelivery.Status.FAILED,
                last_error="Destination unroutable",
            )

            # 3. Late transfer (open and dispatched 5 hours ago)
            s3 = SampleFactory(branch=b1)
            SampleTransferFactory(
                sample=s3,
                from_branch=b1,
                to_branch=b2,
                status=SampleTransfer.Status.OPEN,
                dispatched_at=timezone.now() - timedelta(hours=5),
            )

            # 4. Critical result unacknowledged
            s4 = SampleFactory(branch=b1)
            t4 = TestFactory(name="Potassium (K+)")
            ResultFactory(
                sample=s4,
                test=t4,
                value="6.8",
                unit="mmol/L",
                flag=Result.Flag.CRITICAL,
                status=Result.Status.APPROVED,
            )

            # 5. Stuck sample (collected 6 hours ago with no advancement)
            SampleFactory(
                branch=b1,
                status=Sample.Status.COLLECTED,
                collected_at=timezone.now() - timedelta(hours=6),
            )

        response = api_client.get("/api/v1/exceptions")
        assert response.status_code == 200
        data = response.json()
        assert data["counts"]["total"] >= 5
        kinds = {item["kind"] for item in data["results"]}
        assert "failed_generation" in kinds
        assert "failed_delivery" in kinds
        assert "late_transfer" in kinds
        assert "critical_unacknowledged" in kinds
        assert "stuck_sample" in kinds
