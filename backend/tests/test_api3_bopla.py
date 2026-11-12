"""API3 BOPLA regression tests (LAB-49 Phase 5.1–5.3).

- Unknown input fields are rejected with 422 on every migrated write serializer.
- Per-role output allowlists hide PII from Technician/Pathologist responses.
- ``deleted_at`` is gone from the patient detail payload.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Role
from apps.billing.serializers import InvoiceDetailSerializer
from apps.core.serializers import StrictSerializer
from apps.patients.serializers import PatientDetailSerializer
from tests.factories.patients import PatientFactory


def _request_for(role: str) -> SimpleNamespace:
    return SimpleNamespace(user=SimpleNamespace(role=role))


@pytest.mark.django_db
class TestStrictSerializers:
    def test_patient_create_rejects_unknown_field(self) -> None:
        from apps.patients.serializers import PatientCreateSerializer

        serializer = PatientCreateSerializer(
            data={
                "name": "Test Patient",
                "phone": "03001234567",
                "sex": "M",
                "branch_id": "00000000-0000-0000-0000-000000000001",
                # mass-assignment probe: a field the serializer must not accept
                "role": "owner",
            }
        )
        assert serializer.is_valid() is False
        assert "role" in str(serializer.errors).lower()

    def test_migrated_serializers_inherit_the_strict_base(self) -> None:
        from apps.accounts.serializers_auth import LoginRequestSerializer
        from apps.catalog.serializers import (
            PanelCreateSerializer,
            TestCreateSerializer,
            TestPriceCreateSerializer,
            TestUpdateSerializer,
        )

        for serializer_class in (
            LoginRequestSerializer,
            TestCreateSerializer,
            TestUpdateSerializer,
            PanelCreateSerializer,
            TestPriceCreateSerializer,
        ):
            assert issubclass(serializer_class, StrictSerializer)


@pytest.mark.django_db
class TestPerRoleOutputAllowlist:
    def test_technician_patient_detail_hides_pii(self, tenant_a: Any) -> None:
        with schema_context(tenant_a.schema_name):
            patient = PatientFactory()

            technician_data = PatientDetailSerializer(
                patient, context={"request": _request_for(Role.TECHNICIAN)}
            ).data
            owner_data = PatientDetailSerializer(
                patient, context={"request": _request_for(Role.OWNER)}
            ).data

        assert technician_data["phone"] is None
        assert technician_data["date_of_birth"] is None
        assert technician_data["contacts"] == []
        assert technician_data["consents"] == []
        assert "deleted_at" not in technician_data
        assert "deleted_at" not in owner_data
        assert owner_data["phone"] == patient.phone

    def test_technician_invoice_detail_hides_pii(self) -> None:
        payload = {
            "id": "00000000-0000-0000-0000-000000000001",
            "invoice_number": "INV-1",
            "patient_id": "00000000-0000-0000-0000-000000000002",
            "patient_name": "Test Patient",
            "patient_mrn": "MRN-1",
            "patient_sex": "M",
            "patient_age": "30",
            "patient_phone": "03001234567",
            "branch_id": "00000000-0000-0000-0000-000000000003",
            "branch_name": "Main",
            "referral_partner_id": None,
            "status": "unpaid",
            "subtotal": "100.00",
            "discount_amount": "0.00",
            "discount_reason": "staff waiver",
            "total": "100.00",
            "items": [],
            "payments": [],
            "net_paid": "0.00",
            "created_at": "2026-01-01T00:00:00Z",
        }
        technician_data = InvoiceDetailSerializer(
            payload, context={"request": _request_for(Role.TECHNICIAN)}
        ).data
        owner_data = InvoiceDetailSerializer(
            payload, context={"request": _request_for(Role.OWNER)}
        ).data

        assert technician_data["patient_phone"] is None
        assert technician_data["patient_age"] is None
        assert technician_data["discount_reason"] is None
        assert owner_data["patient_phone"] == "03001234567"

    def test_patient_list_summary_applies_same_role_mask(self, tenant_a: Any) -> None:
        from apps.patients.serializers import PatientSummarySerializer

        with schema_context(tenant_a.schema_name):
            patient = PatientFactory()
            technician_data = PatientSummarySerializer(
                patient, context={"request": _request_for(Role.TECHNICIAN)}
            ).data
            owner_data = PatientSummarySerializer(
                patient, context={"request": _request_for(Role.OWNER)}
            ).data

        assert technician_data["phone"] is None
        assert technician_data["date_of_birth"] is None
        assert technician_data["year_of_birth"] is None
        assert owner_data["phone"] == patient.phone
