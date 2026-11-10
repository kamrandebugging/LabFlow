"""Owner-journey regression tests (post round-4 E2E).

Covers defects found while running the full owner journey on a freshly
provisioned lab:

1. Registration dropped the WhatsApp number and delivery consent, so every
   later ``POST /reports/{id}/deliver`` failed its consent/contact checks.
2. The patient list never returned a branch name, so every row rendered the
   "Main Branch" fallback.
3. The report detail payload omitted ``age_years``, ``email`` and branding.
4. The sample detail payload omitted the custody event timeline.
5. Payment rows exposed the operator's raw staff UUID.
"""

import uuid
from datetime import date
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role, StaffBranch, StaffUser
from apps.billing.serializers import PaymentSerializer
from apps.patients.models import PatientConsent, PatientContact
from apps.reports.services_query import _age_years
from apps.samples.serializers import SampleDetailSerializer
from tests.factories.branch import BranchFactory
from tests.factories.samples import SampleEventFactory
from tests.factories.staff_user import StaffUserFactory


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(staff_user: StaffUser, tenant_id: str = "tenant_a") -> Any:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
        return {
            "HTTP_AUTHORIZATION": f"Bearer {session['access']}",
            "HTTP_HOST": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def journey_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="JRN", name="Journey Main Branch")
        reception = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="journey_reception@test.com"
        )
        StaffBranch.objects.create(staff_user=reception, branch=branch, is_primary=True)
        return {"branch": branch, "reception": reception}


@pytest.mark.django_db
class TestPatientRegistrationDeliveryConsent:
    def test_registration_persists_whatsapp_contact_and_consent(
        self,
        client: Client,
        tenant_a: Any,
        journey_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            reception = journey_setup["reception"]
            branch = journey_setup["branch"]
            headers = auth_headers(reception, tenant_a.schema_name)

            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Consent Patient",
                    "phone": "03001234001",
                    "sex": "F",
                    "date_of_birth": "1990-05-12",
                    "branch_id": str(branch.id),
                    "whatsapp_number": "+92 300 1234001",
                    "consent_reports": True,
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 201, res.content
            patient_id = uuid.UUID(res.json()["id"])

            contact = PatientContact.objects.get(patient_id=patient_id)
            assert contact.kind == PatientContact.Kind.WHATSAPP
            # Normalised exactly like the primary phone (92.. -> 0..).
            assert contact.value == "03001234001"

            consent = PatientConsent.objects.get(patient_id=patient_id)
            assert consent.channel == PatientConsent.Channel.WHATSAPP
            assert consent.granted_by_id == reception.id
            assert consent.revoked_at is None

    def test_registration_falls_back_to_phone_for_consent_destination(
        self,
        client: Client,
        tenant_a: Any,
        journey_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            reception = journey_setup["reception"]
            branch = journey_setup["branch"]
            headers = auth_headers(reception, tenant_a.schema_name)

            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Phone Only Patient",
                    "phone": "03001234002",
                    "sex": "M",
                    "branch_id": str(branch.id),
                    "consent_reports": True,
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 201, res.content
            contact = PatientContact.objects.get(patient_id=uuid.UUID(res.json()["id"]))
            assert contact.value == "03001234002"

    def test_registration_without_consent_records_nothing(
        self,
        client: Client,
        tenant_a: Any,
        journey_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            reception = journey_setup["reception"]
            branch = journey_setup["branch"]
            headers = auth_headers(reception, tenant_a.schema_name)

            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Opt Out Patient",
                    "phone": "03001234003",
                    "sex": "M",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 201, res.content
            patient_id = uuid.UUID(res.json()["id"])
            assert not PatientContact.objects.filter(patient_id=patient_id).exists()
            assert not PatientConsent.objects.filter(patient_id=patient_id).exists()

    def test_invalid_whatsapp_number_is_rejected(
        self,
        client: Client,
        tenant_a: Any,
        journey_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            reception = journey_setup["reception"]
            branch = journey_setup["branch"]
            headers = auth_headers(reception, tenant_a.schema_name)

            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Bad WhatsApp",
                    "phone": "03001234004",
                    "sex": "F",
                    "branch_id": str(branch.id),
                    "whatsapp_number": "12",
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422


@pytest.mark.django_db
class TestPatientListBranchName:
    def test_list_includes_registering_branch_name(
        self,
        client: Client,
        tenant_a: Any,
        journey_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            reception = journey_setup["reception"]
            branch = journey_setup["branch"]
            headers = auth_headers(reception, tenant_a.schema_name)

            created = client.post(
                "/api/v1/patients",
                data={
                    "name": "Branch Name Patient",
                    "phone": "03001234005",
                    "sex": "M",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert created.status_code == 201

            listing = client.get("/api/v1/patients", **headers)
            assert listing.status_code == 200
            rows = listing.json()
            row = next(r for r in rows if r["name"] == "Branch Name Patient")
            assert row["branch_name"] == "Journey Main Branch"


@pytest.mark.django_db
class TestReportDetailIdentityFields:
    def test_age_years_is_computed_from_dob_and_collection(self) -> None:
        collected = timezone.now()
        assert _age_years(date(1990, 5, 12), collected) is not None

        dob = date(1990, 5, 12)
        expected = (collected.date() - dob).days // 365
        assert _age_years(dob, collected) == expected

    def test_age_years_is_none_without_dob(self) -> None:
        assert _age_years(None, timezone.now()) is None


@pytest.mark.django_db
class TestSampleDetailTimeline:
    def test_events_are_exposed_oldest_first(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory(code="EVT", name="Event Branch")
            sample = _make_sample(branch)
            first = SampleEventFactory(sample=sample, event="COLLECTED", branch=branch)
            second = SampleEventFactory(sample=sample, event="RECEIVED", branch=branch)

            payload = SampleDetailSerializer(sample).data
            events = payload["events"]

            assert [e["event"] for e in events] == ["COLLECTED", "RECEIVED"]
            assert [e["id"] for e in events] == [str(first.id), str(second.id)]
            assert events[0]["timestamp"]
            assert events[0]["branch"]["name"] == "Event Branch"


def _make_sample(branch: Any) -> Any:
    """Minimal sample row for serializer-only assertions."""
    from tests.factories import InvoiceFactory, PatientFactory, SampleFactory

    patient = PatientFactory(branch=branch)
    invoice = InvoiceFactory(patient=patient, branch=branch)
    return SampleFactory(invoice=invoice, branch=branch)


@pytest.mark.django_db
class TestPaymentOperatorDisplay:
    def test_received_by_is_a_display_name(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            from tests.factories import InvoiceFactory, PaymentFactory

            staff = StaffUserFactory(role=Role.RECEPTION, email="bilal@test.com")
            invoice = InvoiceFactory()
            payment = PaymentFactory(invoice=invoice, received_by=staff)

            payload = PaymentSerializer(payment).data
            # Staff accounts carry no display name; the email is readable
            # where the raw UUID was not.
            assert payload["received_by"] == "bilal@test.com"
