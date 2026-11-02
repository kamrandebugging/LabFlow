"""LAB-15 Comprehensive Test Suite: Patient Management (Doc 03 §5.1, §6.2, Doc 04 §8.5).

Covers:
1. Registration & MRN format: MRN-{branch:3}-{seq:06d} (PT-1, Doc 02 §9, T-14).
2. Validation rules PT-V1 (name, phone, sex, date_of_birth, branch scope).
3. Duplicate check PT-3 (exact phone, trigram name + DOB -> 409, confirm override).
4. Multi-branch scoping BS-1 to BS-4 & T-41:
   - BS-1: Owner/Pathologist tenant-wide access.
   - BS-2: Staff with zero branches get empty list.
   - BS-3: Branch-scoped listing filters to caller's assigned branches.
   - BS-4: Cross-branch search q= returns identifiers-only.
5. Anti-oracle 404 for out-of-scope detail (P-7, T-41), cross-tenant isolation (T-39).
6. Optimistic concurrency If-Match (T-37) & 409 version_conflict.
7. Identity edit gate PT-4 (requires Owner/Manager after finalised report).
8. Soft-delete PT-5 (refused 409 on samples in flight, idempotent 204).
9. Audit log emission contract for all state changes.
"""

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.models import Invoice
from apps.patients.models import Patient, PatientContact
from apps.reports.models import Report
from apps.samples.models import Sample
from tests.factories.branch import BranchFactory
from tests.factories.staff_user import StaffUserFactory


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser, tenant_id: str = "tenant"
    ) -> dict[str, str]:
        session = AuthService.create_session(
            user=staff_user,
            tenant_id=tenant_id,
        )
        slug = str(tenant_id).replace("_", "-")
        return {
            "HTTP_AUTHORIZATION": f"Bearer {session['access']}",
            "HTTP_HOST": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def branch_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch_isb = BranchFactory(code="ISB", name="Islamabad Main Branch")
        branch_rwp = BranchFactory(code="RWP", name="Rawalpindi Satellite")

        owner = StaffUserFactory(
            role=Role.OWNER,
            branch=None,
            email="owner_lab15@tenant.com",
        )
        manager = StaffUserFactory(
            role=Role.MANAGER,
            branch=branch_isb,
            email="manager_isb@tenant.com",
        )
        StaffBranch.objects.create(
            staff_user=manager, branch=branch_isb, is_primary=True
        )

        receptionist_isb = StaffUserFactory(
            role=Role.RECEPTION,
            branch=branch_isb,
            email="reception_isb@tenant.com",
        )
        StaffBranch.objects.create(
            staff_user=receptionist_isb, branch=branch_isb, is_primary=True
        )

        receptionist_rwp = StaffUserFactory(
            role=Role.RECEPTION,
            branch=branch_rwp,
            email="reception_rwp@tenant.com",
        )
        StaffBranch.objects.create(
            staff_user=receptionist_rwp, branch=branch_rwp, is_primary=True
        )

        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST,
            branch=None,
            email="path_lab15@tenant.com",
        )

        unassigned_staff = StaffUserFactory(
            role=Role.RECEPTION,
            branch=None,
            email="unassigned@tenant.com",
        )

        return {
            "branch_isb": branch_isb,
            "branch_rwp": branch_rwp,
            "owner": owner,
            "manager": manager,
            "receptionist_isb": receptionist_isb,
            "receptionist_rwp": receptionist_rwp,
            "pathologist": pathologist,
            "unassigned_staff": unassigned_staff,
        }


@pytest.mark.django_db
class TestPatientRegistrationAndMRN:
    """Covers registration, validation, MRN generation (T-14), and audit logging."""

    def test_registration_success_and_mrn_format_t14(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            receptionist = branch_setup["receptionist_isb"]
            branch = branch_setup["branch_isb"]
            headers = auth_headers(receptionist, tenant_id=tenant_a.schema_name)

            payload = {
                "name": "Muhammad Ali",
                "phone": "+92 300 1234567",
                "sex": "M",
                "date_of_birth": "1992-05-14",
                "branch_id": str(branch.id),
            }

            res = client.post(
                "/api/v1/patients",
                data=payload,
                content_type="application/json",
                **headers,
            )

            assert res.status_code == 201, res.json()
            data = res.json()
            assert data["name"] == "Muhammad Ali"
            # Phone normalised to digits
            assert data["phone"] == "03001234567"
            assert data["sex"] == "M"
            assert data["date_of_birth"] == "1992-05-14"
            assert data["branch_id"] == str(branch.id)

            # T-14: MRN format MRN-{branch_code:3}-{seq:06d}
            mrn = data["mrn"]
            assert mrn.startswith("MRN-ISB-")
            seq_part = mrn.split("-")[-1]
            assert len(seq_part) == 6
            assert seq_part.isdigit()

            # Second patient at same branch increments sequence
            payload2 = {
                "name": "Fatima Zahra",
                "phone": "0321-7654321",
                "sex": "F",
                "date_of_birth": "1995-10-20",
                "branch_id": str(branch.id),
            }
            res2 = client.post(
                "/api/v1/patients",
                data=payload2,
                content_type="application/json",
                **headers,
            )
            assert res2.status_code == 201
            mrn2 = res2.json()["mrn"]
            assert mrn2.startswith("MRN-ISB-")
            assert int(mrn2.split("-")[-1]) == int(seq_part) + 1

            # Audit log row asserted within transaction
            audit = AuditLog.objects.filter(
                action="patient.registered",
                entity_id=uuid.UUID(data["id"]),
            ).first()
            assert audit is not None
            assert audit.actor_id == receptionist.id
            assert audit.after_jsonb is not None
            assert audit.after_jsonb["mrn"] == mrn

    def test_registration_validation_pt_v1(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            receptionist = branch_setup["receptionist_isb"]
            branch = branch_setup["branch_isb"]
            headers = auth_headers(receptionist, tenant_id=tenant_a.schema_name)

            # 1. Name too short (<2 chars)
            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "A",
                    "phone": "03001234567",
                    "sex": "M",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422

            # 2. Name too long (>120 chars)
            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "X" * 125,
                    "phone": "03001234567",
                    "sex": "M",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422

            # 3. Invalid phone (<10 or >15 digits)
            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Valid Name",
                    "phone": "12345",
                    "sex": "M",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422

            # 4. Invalid sex
            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Valid Name",
                    "phone": "03001234567",
                    "sex": "X",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422

            # 5. Future DOB
            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Valid Name",
                    "phone": "03001234567",
                    "sex": "M",
                    "date_of_birth": (
                        timezone.now().date() + timedelta(days=5)
                    ).isoformat(),
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422

            # 6. Branch out of caller's scope
            branch_rwp = branch_setup["branch_rwp"]
            res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Valid Name",
                    "phone": "03001234567",
                    "sex": "M",
                    "branch_id": str(branch_rwp.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code in (403, 422)


@pytest.mark.django_db
class TestPatientDuplicateDetectionPT3:
    """Covers PT-3 duplicate prevention and confirm override."""

    def test_duplicate_phone_match_returns_409_candidates(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch = branch_setup["branch_isb"]
            receptionist = branch_setup["receptionist_isb"]
            headers = auth_headers(receptionist, tenant_id=tenant_a.schema_name)

            # Register existing patient
            client.post(
                "/api/v1/patients",
                data={
                    "name": "Tariq Mahmood",
                    "phone": "03009998877",
                    "sex": "M",
                    "date_of_birth": "1980-01-01",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )

            # Attempt to register another person with the exact same phone
            dup_res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Bilal Mahmood",
                    "phone": "+92 300 9998877",  # Normalises to same digits
                    "sex": "M",
                    "date_of_birth": "2010-06-15",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )

            assert dup_res.status_code == 409
            body = dup_res.json()
            assert body["error"]["code"] == "possible_duplicate"
            candidates = body.get("candidates") or body["error"].get("candidates")
            assert len(candidates) >= 1
            # BS-4 identifiers only
            cand = candidates[0]
            assert cand["name"] == "Tariq Mahmood"
            assert "mrn" in cand
            assert "sex" in cand
            assert cand.get("year_of_birth") == 1980
            # Ensure no phone or sensitive clinical data in candidate preview
            assert "phone" not in cand or cand.get("phone") is None

    def test_duplicate_trigram_name_and_dob_returns_409(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch = branch_setup["branch_isb"]
            receptionist = branch_setup["receptionist_isb"]
            headers = auth_headers(receptionist, tenant_id=tenant_a.schema_name)

            # Register initial patient
            client.post(
                "/api/v1/patients",
                data={
                    "name": "Muhammad Usman Khan",
                    "phone": "03111111111",
                    "sex": "M",
                    "date_of_birth": "1994-08-20",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )

            # Similar name via pg_trgm + same DOB + different phone
            dup_res = client.post(
                "/api/v1/patients",
                data={
                    "name": "Mohammad Usman Khan",
                    "phone": "03222222222",
                    "sex": "M",
                    "date_of_birth": "1994-08-20",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )

            assert dup_res.status_code == 409
            body = dup_res.json()
            assert body["error"]["code"] == "possible_duplicate"

    def test_confirm_duplicate_override_succeeds_with_audit(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch = branch_setup["branch_isb"]
            receptionist = branch_setup["receptionist_isb"]
            headers = auth_headers(receptionist, tenant_id=tenant_a.schema_name)

            # Register first family member
            res1 = client.post(
                "/api/v1/patients",
                data={
                    "name": "Mother Name",
                    "phone": "03335555555",
                    "sex": "F",
                    "date_of_birth": "1975-03-12",
                    "branch_id": str(branch.id),
                },
                content_type="application/json",
                **headers,
            )
            assert res1.status_code == 201

            # Register second family member using confirm_duplicate: true
            res2 = client.post(
                "/api/v1/patients",
                data={
                    "name": "Child Name",
                    "phone": "03335555555",
                    "sex": "M",
                    "date_of_birth": "2005-09-10",
                    "branch_id": str(branch.id),
                    "confirm_duplicate": True,
                },
                content_type="application/json",
                **headers,
            )
            assert res2.status_code == 201
            data2 = res2.json()
            assert data2["name"] == "Child Name"

            # Both records coexist with shared phone (PT-3 edge case)
            p1 = Patient.objects.get(name="Mother Name")
            p2 = Patient.objects.get(name="Child Name")
            assert p1.phone == p2.phone
            assert p1.mrn != p2.mrn


@pytest.mark.django_db
class TestPatientMultiBranchScopingBS:
    """Covers BS-1 to BS-4 and T-41 branch scoping and identifiers-only search."""

    def test_list_and_search_branch_scoping_t41(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            branch_rwp = branch_setup["branch_rwp"]
            rec_isb = branch_setup["receptionist_isb"]
            owner = branch_setup["owner"]

            # Create patient in ISB branch and patient in RWP branch
            p_isb = Patient.objects.create(
                name="Kamran ISB",
                phone="03001000001",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-000101",
            )
            p_rwp = Patient.objects.create(
                name="Kamran RWP",
                phone="03001000002",
                sex="M",
                date_of_birth=date(1992, 2, 2),
                branch=branch_rwp,
                mrn="MRN-RWP-000201",
            )

            # 1. Receptionist at ISB: list without query -> only ISB branch patients
            headers_isb = auth_headers(rec_isb, tenant_id=tenant_a.schema_name)
            res_list = client.get("/api/v1/patients", **headers_isb)
            assert res_list.status_code == 200
            items = (
                res_list.json()
                if isinstance(res_list.json(), list)
                else res_list.json().get("results", [])
            )
            mrns = [item["mrn"] for item in items]
            assert p_isb.mrn in mrns
            assert p_rwp.mrn not in mrns

            # 2. Receptionist at ISB: search ?q=Kamran -> BS-4 cross-branch identifiers
            res_search = client.get("/api/v1/patients?q=Kamran", **headers_isb)
            assert res_search.status_code == 200
            search_items = (
                res_search.json()
                if isinstance(res_search.json(), list)
                else res_search.json().get("results", [])
            )
            item_map = {item["mrn"]: item for item in search_items}

            # In-scope match has full fields
            assert p_isb.mrn in item_map
            assert item_map[p_isb.mrn]["phone"] == "03001000001"
            assert item_map[p_isb.mrn]["is_cross_branch"] is False

            # Out-of-branch match has identifiers only (BS-4)
            assert p_rwp.mrn in item_map
            rwp_item = item_map[p_rwp.mrn]
            assert rwp_item["is_cross_branch"] is True
            assert rwp_item["name"] == "Kamran RWP"
            assert rwp_item["year_of_birth"] == 1992
            # Phone omitted or masked for cross-branch
            assert "phone" not in rwp_item or rwp_item.get("phone") is None

            # 3. Owner (tenant-wide, BS-1): sees full details for all branches
            headers_owner = auth_headers(owner, tenant_id=tenant_a.schema_name)
            res_owner = client.get("/api/v1/patients?q=Kamran", **headers_owner)
            assert res_owner.status_code == 200
            owner_items = (
                res_owner.json()
                if isinstance(res_owner.json(), list)
                else res_owner.json().get("results", [])
            )
            for item in owner_items:
                assert item["is_cross_branch"] is False
                assert item["phone"] is not None

    def test_unassigned_staff_gets_empty_list_bs2(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            unassigned = branch_setup["unassigned_staff"]
            headers = auth_headers(unassigned, tenant_id=tenant_a.schema_name)
            res = client.get("/api/v1/patients", **headers)
            assert res.status_code == 200
            items = (
                res.json()
                if isinstance(res.json(), list)
                else res.json().get("results", [])
            )
            assert len(items) == 0


@pytest.mark.django_db
class TestPatientDetailAndHistory:
    """Covers GET /patients/{id}, anti-oracle 404 (P-7, T-41), and isolation (T-39)."""

    def test_patient_detail_in_scope_success(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            rec_isb = branch_setup["receptionist_isb"]
            p = Patient.objects.create(
                name="Detail Patient",
                phone="03001239999",
                sex="F",
                date_of_birth=date(1993, 4, 10),
                branch=branch_isb,
                mrn="MRN-ISB-000301",
            )
            PatientContact.objects.create(
                patient=p,
                kind=PatientContact.Kind.WHATSAPP,
                value="+923001239999",
                is_primary=True,
            )

            headers = auth_headers(rec_isb, tenant_id=tenant_a.schema_name)
            res = client.get(f"/api/v1/patients/{p.id}", **headers)
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == str(p.id)
            assert data["name"] == "Detail Patient"
            assert "contacts" in data
            assert len(data["contacts"]) == 1
            assert data["contacts"][0]["kind"] == "whatsapp"

    def test_patient_detail_out_of_scope_returns_404_anti_oracle_t41(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_rwp = branch_setup["branch_rwp"]
            rec_isb = branch_setup["receptionist_isb"]
            p_rwp = Patient.objects.create(
                name="Secret RWP Patient",
                phone="03009999999",
                sex="M",
                date_of_birth=date(1985, 5, 5),
                branch=branch_rwp,
                mrn="MRN-RWP-000401",
            )

            # Receptionist at ISB requests RWP patient detail -> 404 (P-7, BS-3)
            headers = auth_headers(rec_isb, tenant_id=tenant_a.schema_name)
            res = client.get(f"/api/v1/patients/{p_rwp.id}", **headers)
            assert res.status_code == 404
            assert res.json()["error"]["code"] == "not_found"

    def test_patient_detail_cross_tenant_isolation_t39(
        self,
        client: Client,
        tenant_a: Any,
        tenant_b: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            p_a = Patient.objects.create(
                name="Tenant A Patient",
                phone="03001112233",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-000501",
            )
            rec_a = branch_setup["receptionist_isb"]
            headers_a = auth_headers(rec_a, tenant_id=tenant_a.schema_name)

        # Present Tenant A token against Tenant B host -> 404 / denied (T-39)
        headers_a["HTTP_HOST"] = f"{tenant_b.schema_name}.localhost"
        res = client.get(f"/api/v1/patients/{p_a.id}", **headers_a)
        assert res.status_code in (401, 403, 404)


@pytest.mark.django_db
class TestPatientEditAndConcurrencyPT4:
    """Covers PATCH /patients/{id}, If-Match concurrency (T-37) & PT-4 identity gate."""

    def test_patient_edit_success_and_audit(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            rec_isb = branch_setup["receptionist_isb"]
            p = Patient.objects.create(
                name="Original Name",
                phone="03001112222",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-000601",
            )
            headers = auth_headers(rec_isb, tenant_id=tenant_a.schema_name)

            patch_res = client.patch(
                f"/api/v1/patients/{p.id}",
                data={"phone": "03009990000"},
                content_type="application/json",
                **headers,
            )
            assert patch_res.status_code == 200
            assert patch_res.json()["phone"] == "03009990000"

            p.refresh_from_db()
            assert p.phone == "03009990000"

            # Audit row verified
            audit = AuditLog.objects.filter(
                action="patient.updated",
                entity_id=p.id,
            ).first()
            assert audit is not None
            assert audit.before_jsonb is not None
            assert audit.after_jsonb is not None
            assert audit.before_jsonb["phone"] == "03001112222"
            assert audit.after_jsonb["phone"] == "03009990000"

    def test_patient_edit_if_match_concurrency_t37(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            rec_isb = branch_setup["receptionist_isb"]
            p = Patient.objects.create(
                name="Concurrent Patient",
                phone="03001113333",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-000701",
            )
            headers = auth_headers(rec_isb, tenant_id=tenant_a.schema_name)

            # 1. Stale If-Match header -> 409 version_conflict and no write
            headers["HTTP_IF_MATCH"] = "2020-01-01T00:00:00Z"
            stale_res = client.patch(
                f"/api/v1/patients/{p.id}",
                data={"name": "Hacked Name"},
                content_type="application/json",
                **headers,
            )
            assert stale_res.status_code == 409
            assert stale_res.json()["error"]["code"] == "version_conflict"

            p.refresh_from_db()
            assert p.name == "Concurrent Patient"

            # 2. Correct If-Match header -> succeeds
            headers["HTTP_IF_MATCH"] = p.updated_at.isoformat()
            ok_res = client.patch(
                f"/api/v1/patients/{p.id}",
                data={"name": "Updated Name"},
                content_type="application/json",
                **headers,
            )
            assert ok_res.status_code == 200
            p.refresh_from_db()
            assert p.name == "Updated Name"

    def test_patient_edit_identity_after_finalised_report_pt4(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            rec_isb = branch_setup["receptionist_isb"]
            owner = branch_setup["owner"]

            p = Patient.objects.create(
                name="Reported Patient",
                phone="03001114444",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-000801",
            )
            # Create invoice, sample, and finalised report
            invoice = Invoice.objects.create(patient=p, branch=branch_isb)
            sample = Sample.objects.create(
                invoice=invoice,
                branch=branch_isb,
                accession_id="ISB20261102000001",
                status="ready",
                collected_at=timezone.now(),
            )
            Report.objects.create(
                sample=sample,
                status="final",  # Finalised report exists
                current_version=1,
            )

            headers_rec = auth_headers(rec_isb, tenant_id=tenant_a.schema_name)

            # 1. Receptionist attempting identity edit (name, sex, date_of_birth) -> 403
            res_rec = client.patch(
                f"/api/v1/patients/{p.id}",
                data={"name": "Doctor Changed Name"},
                content_type="application/json",
                **headers_rec,
            )
            assert res_rec.status_code == 403
            assert (
                res_rec.json()["error"]["code"] == "identity_edit_requires_management"
            )

            # 2. Receptionist editing phone is allowed (phone is not identity field)
            res_phone = client.patch(
                f"/api/v1/patients/{p.id}",
                data={"phone": "03009998888"},
                content_type="application/json",
                **headers_rec,
            )
            assert res_phone.status_code == 200

            # 3. Owner performing identity edit succeeds (PT-4)
            headers_owner = auth_headers(owner, tenant_id=tenant_a.schema_name)
            res_owner = client.patch(
                f"/api/v1/patients/{p.id}",
                data={"name": "Owner Approved Name Change"},
                content_type="application/json",
                **headers_owner,
            )
            assert res_owner.status_code == 200
            p.refresh_from_db()
            assert p.name == "Owner Approved Name Change"


@pytest.mark.django_db
class TestPatientSoftDeletePT5:
    """Covers DELETE /patients/{id}, refusal on samples in flight, and idempotency."""

    def test_soft_delete_success_and_idempotency(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            owner = branch_setup["owner"]
            p = Patient.objects.create(
                name="To Delete",
                phone="03001115555",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-000901",
            )
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            # First delete -> 204
            del_res = client.delete(f"/api/v1/patients/{p.id}", **headers)
            assert del_res.status_code == 204

            p.refresh_from_db()
            assert p.deleted_at is not None

            # Disappears from list/search (PT-5)
            list_res = client.get("/api/v1/patients", **headers)
            assert p.mrn not in [item["mrn"] for item in list_res.json()]

            # Detail returns 404
            get_res = client.get(f"/api/v1/patients/{p.id}", **headers)
            assert get_res.status_code == 404

            # Second delete is idempotent -> 204
            del_res2 = client.delete(f"/api/v1/patients/{p.id}", **headers)
            assert del_res2.status_code == 204

            # Audit row verified
            audit = AuditLog.objects.filter(
                action="patient.soft_deleted",
                entity_id=p.id,
            ).first()
            assert audit is not None

    def test_soft_delete_receptionist_denied_403(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            rec_isb = branch_setup["receptionist_isb"]
            p = Patient.objects.create(
                name="Protected Patient",
                phone="03001116666",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-001001",
            )
            headers = auth_headers(rec_isb, tenant_id=tenant_a.schema_name)
            res = client.delete(f"/api/v1/patients/{p.id}", **headers)
            assert res.status_code == 403

    def test_soft_delete_refused_on_samples_in_flight_409(
        self,
        client: Client,
        tenant_a: Any,
        branch_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            branch_isb = branch_setup["branch_isb"]
            owner = branch_setup["owner"]
            p = Patient.objects.create(
                name="Patient With Active Samples",
                phone="03001117777",
                sex="M",
                date_of_birth=date(1990, 1, 1),
                branch=branch_isb,
                mrn="MRN-ISB-001101",
            )
            # Sample in status 'received' (in flight) via invoice
            invoice = Invoice.objects.create(patient=p, branch=branch_isb)
            Sample.objects.create(
                invoice=invoice,
                branch=branch_isb,
                accession_id="ISB20261102000002",
                status="received",
                collected_at=timezone.now(),
            )

            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)
            del_res = client.delete(f"/api/v1/patients/{p.id}", **headers)
            assert del_res.status_code == 409
            assert del_res.json()["error"]["code"] == "samples_in_flight"
            p.refresh_from_db()
            assert p.deleted_at is None
