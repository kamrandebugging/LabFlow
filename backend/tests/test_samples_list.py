"""Tests for GET /api/v1/samples endpoint (SM-1..SM-11, Screen 16).

Accepts query params: q, status, branch_id.
Returns: {results: [...], total: N} satisfying SampleSummary.
Tenancy: Tenant-scoped, authenticated staff only, respects branch scope.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, StaffUser
from apps.core.models import Tenant
from apps.samples.models import Sample
from tests.factories.accounts import StaffUserFactory
from tests.factories.billing import InvoiceFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.patients import PatientFactory
from tests.factories.samples import SampleFactory, SampleTestFactory


def _staff_user(**kwargs: Any) -> StaffUser:
    return cast(StaffUser, StaffUserFactory(**kwargs))


@pytest.fixture
def api_client(tenant_a: Tenant) -> APIClient:
    client = APIClient()
    client.defaults["HTTP_HOST"] = "tenant-a.localhost"
    return client


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
        "iss": "labflow",
        "aud": "labflow-api",
    }
    return str(jwt.encode(payload, str(signing_key), algorithm="HS256"))


def _authenticate_client(
    client: APIClient,
    staff: StaffUser,
    tenant: Tenant,
    role: str = Role.OWNER,
) -> None:
    token = _mint_jwt(staff.id, tenant.slug, role)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@pytest.mark.django_db
class TestSamplesListEndpoint:
    """Test suite for GET /api/v1/samples."""

    def test_unauthenticated_request_is_rejected(self, api_client: APIClient) -> None:
        """Unauthenticated request must return 401."""
        response = api_client.get("/api/v1/samples")
        assert response.status_code == 401

    def test_empty_tenant_returns_empty_results_and_zero_total(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        """An empty tenant returns {results: [], total: 0}."""
        with tenant_context(tenant_a):
            staff = _staff_user(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

        response = api_client.get("/api/v1/samples")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["total"] == 0

    def test_samples_list_returns_sample_summary_shape(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        """Each row satisfies the frontend SampleSummary interface."""
        with tenant_context(tenant_a):
            branch = BranchFactory(name="Main Branch", code="MB1")
            staff = _staff_user(role=Role.OWNER, branch=branch)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            patient = PatientFactory(
                branch=branch,
                name="Fatima Noor",
                mrn="MRN-1001",
                sex="F",
            )
            invoice = InvoiceFactory(patient=patient, branch=branch)
            test1 = TestFactory(name="CBC")
            test2 = TestFactory(name="Serum Electrolytes")

            sample = SampleFactory(
                invoice=invoice,
                branch=branch,
                accession_id="ACC-2026-0001",
                status=Sample.Status.COLLECTED,
                collected_at=datetime(2026, 11, 8, 10, 0, tzinfo=UTC),
            )
            SampleTestFactory(sample=sample, test=test1, invoice_item__invoice=invoice)
            SampleTestFactory(sample=sample, test=test2, invoice_item__invoice=invoice)

        response = api_client.get("/api/v1/samples")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        row = data["results"][0]

        assert row["id"] == str(sample.id)
        assert row["accession_id"] == "ACC-2026-0001"
        assert row["invoice_id"] == str(invoice.id)
        assert row["patient_id"] == str(patient.id)
        assert row["patient_name"] == "Fatima Noor"
        assert row["patient_mrn"] == "MRN-1001"
        assert row["branch_id"] == str(branch.id)
        assert row["branch_name"] == "Main Branch"
        assert row["status"] == "collected"
        assert set(row["tests"]) == {"CBC", "Serum Electrolytes"}
        assert "collected_at" in row

    def test_status_filter_works(self, tenant_a: Tenant, api_client: APIClient) -> None:
        """Filtering by ?status= returns only matching samples."""
        with tenant_context(tenant_a):
            branch = BranchFactory(name="Branch A")
            staff = _staff_user(role=Role.OWNER, branch=branch)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            patient = PatientFactory(branch=branch)
            inv = InvoiceFactory(patient=patient, branch=branch)
            s_collected = SampleFactory(
                invoice=inv, branch=branch, status=Sample.Status.COLLECTED
            )
            s_ready = SampleFactory(
                invoice=inv, branch=branch, status=Sample.Status.READY
            )

        resp_collected = api_client.get("/api/v1/samples?status=collected")
        assert resp_collected.status_code == 200
        data = resp_collected.json()
        assert data["total"] == 1
        assert data["results"][0]["id"] == str(s_collected.id)

        resp_ready = api_client.get("/api/v1/samples?status=ready")
        assert resp_ready.status_code == 200
        data_ready = resp_ready.json()
        assert data_ready["total"] == 1
        assert data_ready["results"][0]["id"] == str(s_ready.id)

    def test_awaiting_collection_is_rejected_because_no_such_status_exists(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        """A2 cannot invent a status: Sample.Status has no awaiting_collection."""
        with tenant_context(tenant_a):
            staff = _staff_user(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

        response = api_client.get("/api/v1/samples?status=awaiting_collection")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_branch_id_filter_works(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        """Filtering by ?branch_id= returns only samples for that branch."""
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="Branch 1")
            b2 = BranchFactory(name="Branch 2")
            staff = _staff_user(role=Role.OWNER, branch=None)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            p1 = PatientFactory(branch=b1)
            inv1 = InvoiceFactory(patient=p1, branch=b1)
            s1 = SampleFactory(invoice=inv1, branch=b1)

            p2 = PatientFactory(branch=b2)
            inv2 = InvoiceFactory(patient=p2, branch=b2)
            SampleFactory(invoice=inv2, branch=b2)

        resp = api_client.get(f"/api/v1/samples?branch_id={b1.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["id"] == str(s1.id)

    def test_search_q_filter_works(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        """Search query ?q= searches accession_id, patient name, and MRN."""
        with tenant_context(tenant_a):
            b = BranchFactory()
            staff = _staff_user(role=Role.OWNER, branch=b)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            p1 = PatientFactory(branch=b, name="Tariq Mahmood", mrn="MRN-TARIQ")
            inv1 = InvoiceFactory(patient=p1, branch=b)
            s1 = SampleFactory(invoice=inv1, branch=b, accession_id="ACC-MATCH-123")

            p2 = PatientFactory(branch=b, name="Ayesha Khan", mrn="MRN-AYESHA")
            inv2 = InvoiceFactory(patient=p2, branch=b)
            s2 = SampleFactory(invoice=inv2, branch=b, accession_id="ACC-OTHER-456")

        # Search by accession
        resp = api_client.get("/api/v1/samples?q=MATCH")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["results"][0]["id"] == str(s1.id)

        # Search by patient name
        resp = api_client.get("/api/v1/samples?q=Ayesha")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["results"][0]["id"] == str(s2.id)

        # Search by patient MRN
        resp = api_client.get("/api/v1/samples?q=TARIQ")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["results"][0]["id"] == str(s1.id)

    def test_cross_tenant_isolation(
        self, tenant_a: Tenant, tenant_b: Tenant, api_client: APIClient
    ) -> None:
        """Samples from tenant_b never appear in tenant_a's list."""
        with tenant_context(tenant_a):
            b_a = BranchFactory(name="Tenant A Branch")
            staff_a = _staff_user(role=Role.OWNER, branch=b_a)
            _authenticate_client(api_client, staff_a, tenant_a, Role.OWNER)

            p_a = PatientFactory(branch=b_a, name="Patient A")
            inv_a = InvoiceFactory(patient=p_a, branch=b_a)
            s_a = SampleFactory(invoice=inv_a, branch=b_a, accession_id="ACC-A-1")

        with tenant_context(tenant_b):
            b_b = BranchFactory(name="Tenant B Branch")
            p_b = PatientFactory(branch=b_b, name="Patient B")
            inv_b = InvoiceFactory(patient=p_b, branch=b_b)
            SampleFactory(invoice=inv_b, branch=b_b, accession_id="ACC-B-1")

        response = api_client.get("/api/v1/samples")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["id"] == str(s_a.id)
        assert data["results"][0]["accession_id"] == "ACC-A-1"

    def test_unauthorized_role_rejected(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        """Staff with an unauthorized role is denied with 403."""
        with tenant_context(tenant_a):
            b_a = BranchFactory(name="Branch A")
            staff = _staff_user(role="unauthorized_role", branch=b_a)
            _authenticate_client(api_client, staff, tenant_a, "unauthorized_role")

        response = api_client.get("/api/v1/samples")
        assert response.status_code == 403

    def test_limit_query_param(self, tenant_a: Tenant, api_client: APIClient) -> None:
        """Query with limit parameter constrains results while preserving total."""
        with tenant_context(tenant_a):
            b_a = BranchFactory(name="Branch A")
            staff = _staff_user(role=Role.OWNER, branch=b_a)
            _authenticate_client(api_client, staff, tenant_a, Role.OWNER)

            p_a = PatientFactory(branch=b_a, name="Patient A")
            inv_a = InvoiceFactory(patient=p_a, branch=b_a)
            SampleFactory(invoice=inv_a, branch=b_a, accession_id="ACC-L-1")
            SampleFactory(invoice=inv_a, branch=b_a, accession_id="ACC-L-2")
            SampleFactory(invoice=inv_a, branch=b_a, accession_id="ACC-L-3")

        response = api_client.get("/api/v1/samples?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["results"]) == 2

    def test_branch_scope_conformance(self) -> None:
        """SampleCollectionView adheres to TN-20 BranchScopedAPIView conformance."""
        from apps.branches.scope_views import assert_branch_scope_conformance

        assert_branch_scope_conformance()
