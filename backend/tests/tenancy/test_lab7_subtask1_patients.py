from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.patients.models import Patient
from tests.factories.accounts import StaffUserFactory
from tests.factories.branches import BranchFactory
from tests.factories.patients import (
    PatientConsentFactory,
    PatientContactFactory,
    PatientFactory,
)


@pytest.mark.django_db
class TestPatientModelsSchemaAndConstraints:
    def test_pg_trgm_extension_installed(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a), connection.cursor() as cursor:
            cursor.execute(
                "SELECT extname FROM pg_extension WHERE extname = 'pg_trgm';"
            )
            row = cursor.fetchone()
            assert row is not None and row[0] == "pg_trgm"

    def test_patient_indexes_and_trigram_opclasses_exist(self, tenant_a: Any) -> None:
        expected_indexes = {
            "patient": {
                "uq_patient_mrn",
                "idx_patient_branch_id",
                "idx_patient_name_trgm",
                "idx_patient_phone_trgm",
                "idx_patient_deleted_at",
            },
            "patient_contact": {
                "idx_patient_contact_patient_id",
            },
            "patient_consent": {
                "idx_patient_consent_patient_id",
                "idx_patient_consent_granted_by",
            },
        }
        with tenant_context(tenant_a), connection.cursor() as cursor:
            for table_name, idx_set in expected_indexes.items():
                cursor.execute(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = %s AND tablename = %s;
                    """,
                    [tenant_a.schema_name, table_name],
                )
                rows = {r[0]: r[1] for r in cursor.fetchall()}
                for expected_idx in idx_set:
                    assert expected_idx in rows, (
                        f"Missing index {expected_idx} on {table_name}"
                    )
                if table_name == "patient":
                    assert "USING gin" in rows["idx_patient_name_trgm"]
                    assert "gin_trgm_ops" in rows["idx_patient_name_trgm"]
                    assert "USING gin" in rows["idx_patient_phone_trgm"]
                    assert "gin_trgm_ops" in rows["idx_patient_phone_trgm"]

    def test_patient_consent_has_no_updated_at_column(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a), connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'patient_consent';
                """,
                [tenant_a.schema_name],
            )
            cols = {r[0] for r in cursor.fetchall()}
            assert "created_at" in cols
            assert "updated_at" not in cols
            assert "deleted_at" not in cols
            assert "granted_by" in cols

    def test_mrn_unique_per_tenant_and_isolated_across_tenants(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        with tenant_context(tenant_a):
            p_a = PatientFactory(mrn="MRN-ABC-000001")
            assert p_a.mrn == "MRN-ABC-000001"
            with pytest.raises(IntegrityError), transaction.atomic():
                PatientFactory(mrn="MRN-ABC-000001")

        with tenant_context(tenant_b):
            p_b = PatientFactory(mrn="MRN-ABC-000001")
            assert p_b.mrn == "MRN-ABC-000001"
            assert Patient.objects.count() == 1

    def test_foreign_key_protect_on_branch_patient_and_staff(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory()
            staff = StaffUserFactory(branch=branch)
            patient = PatientFactory(branch=branch)
            contact = PatientContactFactory(patient=patient)
            consent = PatientConsentFactory(
                patient=patient,
                granted_by=staff,
                granted_at=timezone.now(),
            )
            assert contact.patient_id == patient.id
            assert consent.patient_id == patient.id

            with pytest.raises(ProtectedError):
                branch.delete()

            with pytest.raises(ProtectedError):
                patient.delete()

            with pytest.raises(ProtectedError):
                staff.delete()
