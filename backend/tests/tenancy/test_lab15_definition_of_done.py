"""LAB-15 Definition of Done Verification Suite (KAN-112).

Acceptance Criteria:
1. DoD (LAB-16): Duplicate returns 409 with candidate list (BS-4 identifiers only);
   confirm_duplicate: true proceeds; audit log contract test passes.
2. DoD (LAB-17): Cross-branch search returns identifiers-only;
   out-of-scope detail returns 404; identity edit after finalised report is gated.
3. Soft-delete refused 409 when samples in flight, idempotent 204.
"""

import uuid
from datetime import date
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.models import Invoice
from apps.patients.models import Patient
from apps.reports.models import Report
from apps.samples.models import Sample
from tests.factories.branch import BranchFactory
from tests.factories.staff_user import StaffUserFactory


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(
            user=staff_user,
            tenant_id=tenant_id,
        )
        return {
            "HTTP_AUTHORIZATION": f"Bearer {session['access']}",
            "HTTP_HOST": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def dod_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch_a = BranchFactory(code="BRA", name="Branch Alpha")
        branch_b = BranchFactory(code="BRB", name="Branch Beta")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="dod_owner@test.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch_a, email="dod_manager@test.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch_a, is_primary=True)

        rec_a = StaffUserFactory(
            role=Role.RECEPTION, branch=branch_a, email="dod_reception@test.com"
        )
        StaffBranch.objects.create(staff_user=rec_a, branch=branch_a, is_primary=True)

        return {
            "branch_a": branch_a,
            "branch_b": branch_b,
            "owner": owner,
            "manager": manager,
            "rec_a": rec_a,
        }


@pytest.mark.django_db
class TestLAB15DefinitionOfDone:
    def test_dod_duplicate_candidate_modal_and_audit_contract(
        self,
        client: Client,
        tenant_a: Any,
        dod_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """DoD LAB-16: Duplicate candidate modal (BS-4 identifiers) & audit contract."""
        with tenant_context(tenant_a):
            rec = dod_setup["rec_a"]
            branch = dod_setup["branch_a"]
            headers = auth_headers(rec, tenant_id=tenant_a.schema_name)

            # 1. Register initial patient
            reg_res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Original Patient",
                    "phone": "03001234999",
                    "sex": "M",
                    "date_of_birth": "1991-03-15",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert reg_res.status_code == 201
            p_id = uuid.UUID(reg_res.json()["id"])

            # Verify audit log contract for registration
            reg_audit = AuditLog.objects.filter(
                action="patient.registered",
                entity_id=p_id,
            ).first()
            assert reg_audit is not None
            assert reg_audit.actor_id == rec.id
            assert reg_audit.after_jsonb is not None
            assert reg_audit.after_jsonb["mrn"].startswith("MRN-BRA-")

            # 2. Duplicate registration attempt returns 409 possible_duplicate
            dup_res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Different Name",
                    "phone": "03001234999",
                    "sex": "F",
                    "date_of_birth": "2000-01-01",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert dup_res.status_code == 409
            body = dup_res.json()
            assert body["error"]["code"] == "possible_duplicate"
            candidates = body.get("candidates") or body["error"].get("candidates")
            assert len(candidates) == 1
            cand = candidates[0]
            assert cand["name"] == "Original Patient"
            assert cand["sex"] == "M"
            assert cand["year_of_birth"] == 1991
            assert "phone" not in cand or cand.get("phone") is None

            # 3. Confirm duplicate proceeds and coexists
            confirm_res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Different Name",
                    "phone": "03001234999",
                    "sex": "F",
                    "date_of_birth": "2000-01-01",
                    "branch_id": str(branch.id),
                    "confirm_duplicate": True,
                },
                content_type="application/json",
                **headers,
            )
            assert confirm_res.status_code == 201
            p2_id = uuid.UUID(confirm_res.json()["id"])

            confirm_audit = AuditLog.objects.filter(
                action="patient.registered",
                entity_id=p2_id,
            ).first()
            assert confirm_audit is not None
            assert confirm_audit.after_jsonb is not None
            assert confirm_audit.after_jsonb["duplicate_confirmed"] is True

    def test_dod_cross_branch_identifiers_and_out_of_scope_404(
        self,
        client: Client,
        tenant_a: Any,
        dod_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """DoD LAB-17: Cross-branch identifiers-only, 404, identity edit gated."""
        with tenant_context(tenant_a):
            rec_a = dod_setup["rec_a"]
            branch_a = dod_setup["branch_a"]
            branch_b = dod_setup["branch_b"]
            owner = dod_setup["owner"]
            headers_rec = auth_headers(rec_a, tenant_id=tenant_a.schema_name)

            # In-scope patient at branch A
            p_a = Patient.objects.create(
                name="Patient In Branch A",
                phone="03005550001",
                sex="M",
                date_of_birth=date(1988, 4, 12),
                branch=branch_a,
                mrn="MRN-BRA-000001",
            )

            # Out-of-scope patient at branch B
            p_b = Patient.objects.create(
                name="Patient In Branch B",
                phone="03005550002",
                sex="F",
                date_of_birth=date(1995, 8, 24),
                branch=branch_b,
                mrn="MRN-BRB-000001",
            )

            # Cross-branch search ?q=Patient -> identifiers only for branch B
            search_res = client.get("/api/v1/patients?q=Patient", **headers_rec)
            assert search_res.status_code == 200
            items = {item["mrn"]: item for item in search_res.json()}

            assert items[p_a.mrn]["is_cross_branch"] is False
            assert items[p_a.mrn]["phone"] == "03005550001"

            assert items[p_b.mrn]["is_cross_branch"] is True
            assert items[p_b.mrn]["name"] == "Patient In Branch B"
            assert items[p_b.mrn]["year_of_birth"] == 1995
            assert "phone" not in items[p_b.mrn] or items[p_b.mrn].get("phone") is None

            # Out-of-scope detail returns anti-oracle 404
            detail_res = client.get(f"/api/v1/patients/{p_b.id}", **headers_rec)
            assert detail_res.status_code == 404
            assert detail_res.json()["error"]["code"] == "not_found"

            # Identity edit after finalised report is gated
            invoice = Invoice.objects.create(patient=p_a, branch=branch_a)
            sample = Sample.objects.create(
                invoice=invoice,
                branch=branch_a,
                accession_id="BRA20261102000001",
                status="ready",
                collected_at=timezone.now(),
            )
            Report.objects.create(
                sample=sample,
                status="final",
                current_version=1,
            )

            # Receptionist editing identity -> 403
            rec_patch = client.patch(
                f"/api/v1/patients/{p_a.id}",
                data={"name": "Tampered Name"},
                content_type="application/json",
                **headers_rec,
            )
            assert rec_patch.status_code == 403
            assert (
                rec_patch.json()["error"]["code"] == "identity_edit_requires_management"
            )

            # Owner editing identity -> 200 + audit row
            headers_owner = auth_headers(owner, tenant_id=tenant_a.schema_name)
            owner_patch = client.patch(
                f"/api/v1/patients/{p_a.id}",
                data={"name": "Owner Verified Name"},
                content_type="application/json",
                **headers_owner,
            )
            assert owner_patch.status_code == 200

            patch_audit = AuditLog.objects.filter(
                action="patient.updated",
                entity_id=p_a.id,
            ).first()
            assert patch_audit is not None
            assert patch_audit.actor_id == owner.id
            assert patch_audit.before_jsonb is not None
            assert patch_audit.after_jsonb is not None
            assert patch_audit.after_jsonb["name"] == "Owner Verified Name"

    def test_dod_soft_delete_and_samples_in_flight_guard(
        self,
        client: Client,
        tenant_a: Any,
        dod_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """DoD: Soft-delete is refused 409 when samples in flight, idempotent 204."""
        with tenant_context(tenant_a):
            manager = dod_setup["manager"]
            branch = dod_setup["branch_a"]
            headers = auth_headers(manager, tenant_id=tenant_a.schema_name)

            p = Patient.objects.create(
                name="Flight Patient",
                phone="03007770001",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch,
                mrn="MRN-BRA-000002",
            )
            invoice = Invoice.objects.create(patient=p, branch=branch)
            Sample.objects.create(
                invoice=invoice,
                branch=branch,
                accession_id="BRA20261102000002",
                status="in_process",  # In-flight status
                collected_at=timezone.now(),
            )

            # Attempt deletion -> 409 samples_in_flight
            del_res = client.delete(f"/api/v1/patients/{p.id}", **headers)
            assert del_res.status_code == 409
            assert del_res.json()["error"]["code"] == "samples_in_flight"

            p.refresh_from_db()
            assert p.deleted_at is None
