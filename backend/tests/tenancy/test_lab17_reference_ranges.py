"""LAB-17 Test Suite: Biological Reference Ranges (Doc 03 §5.2, §8.2; KAN-119).

Covers:
1. GET /api/v1/tests/{id}/ranges read matrix (O, M, R, T, P).
2. POST ranges: Owner + Pathologist only; 403 for Manager/Receptionist/Technician.
3. Field validation (sex, age band order, low<=high, critical bounds, unit,
   effective window) -> 422 validation_error.
4. Overlap rejection (CT-4, CT-V2): same test + overlapping sex + overlapping
   age band + overlapping effective window -> 422 overlapping_range.
5. PATCH supersede semantics: history preserved via close-and-reopen.
6. Audit log contract: catalog.range_created / catalog.range_updated.
7. Deterministic selection service: T-10 future-range exclusion + §8.2 tie-breaks.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.catalog.models import ReferenceRange, Test
from apps.catalog.services import CatalogService
from tests.factories.branch import BranchFactory
from tests.factories.staff_user import StaffUserFactory

TODAY = date(2026, 11, 2)


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
def range_staff(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="RR1", name="Range Laboratory")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="rr_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="rr_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)

        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="rr_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )

        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="rr_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )

        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=None, email="rr_path@tenant.com"
        )

        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "pathologist": pathologist,
        }


@pytest.fixture
def lab_test(tenant_a: Any) -> Test:
    with tenant_context(tenant_a):
        return Test.objects.create(
            code="HB", name="Hemoglobin", category="Hematology", unit="g/dL"
        )


def _range_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sex": "M",
        "age_min_days": 0,
        "age_max_days": 365,
        "low": "13.500",
        "high": "17.500",
        "critical_low": "7.000",
        "critical_high": "20.000",
        "unit": "g/dL",
        "effective_from": "2027-01-01",
        "effective_to": None,
    }
    payload.update(overrides)
    return payload


def _post_range(
    client: Client,
    test_id: uuid.UUID,
    headers: Any,
    **overrides: Any,
) -> Any:
    return client.post(
        f"/api/v1/tests/{test_id}/ranges",
        data=_range_payload(**overrides),
        content_type="application/json",
        **headers,
    )


@pytest.mark.django_db
class TestReferenceRangeList:
    def test_list_ranges_read_matrix(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """GET ranges readable by O, M, R, T, P."""
        with tenant_context(tenant_a):
            owner = range_staff["owner"]
            CatalogService.create_reference_range(
                test_id=lab_test.id,
                sex="M",
                age_min_days=0,
                age_max_days=365,
                low=Decimal("13.500"),
                high=Decimal("17.500"),
                critical_low=Decimal("7.000"),
                critical_high=Decimal("20.000"),
                unit="g/dL",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                actor=owner,
            )

            for role_key in (
                "owner",
                "manager",
                "receptionist",
                "technician",
                "pathologist",
            ):
                headers = auth_headers(
                    range_staff[role_key], tenant_id=tenant_a.schema_name
                )
                res = client.get(f"/api/v1/tests/{lab_test.id}/ranges", **headers)
                assert res.status_code == 200
                data = res.json()
                assert len(data) == 1
                assert data[0]["sex"] == "M"
                assert data[0]["low"] == "13.500"
                assert data[0]["unit"] == "g/dL"

    def test_list_ranges_unknown_test_404(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            res = client.get(f"/api/v1/tests/{uuid.uuid4()}/ranges", **headers)
            assert res.status_code == 404


@pytest.mark.django_db
class TestReferenceRangeCreate:
    def test_create_range_owner_201_and_audit(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """Owner creates a range -> 201 + catalog.range_created audit row."""
        with tenant_context(tenant_a):
            owner = range_staff["owner"]
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            res = _post_range(client, lab_test.id, headers)
            assert res.status_code == 201
            data = res.json()
            assert data["sex"] == "M"
            assert data["age_min_days"] == 0
            assert data["age_max_days"] == 365
            assert data["low"] == "13.500"
            assert data["high"] == "17.500"
            assert data["critical_low"] == "7.000"
            assert data["critical_high"] == "20.000"
            range_id = uuid.UUID(data["id"])

            audit = AuditLog.objects.filter(
                action="catalog.range_created",
                entity_id=range_id,
            ).first()
            assert audit is not None
            assert audit.actor_id == owner.id
            assert audit.entity_type == "reference_range"
            assert audit.before_jsonb is None
            assert audit.after_jsonb is not None
            assert audit.after_jsonb["sex"] == "M"

    def test_create_range_pathologist_201(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """Pathologist may create ranges."""
        with tenant_context(tenant_a):
            headers = auth_headers(
                range_staff["pathologist"], tenant_id=tenant_a.schema_name
            )
            res = _post_range(client, lab_test.id, headers)
            assert res.status_code == 201

    def test_create_range_forbidden_roles_403(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """Manager, Receptionist, Technician get 403 on POST."""
        with tenant_context(tenant_a):
            for role_key in ("manager", "receptionist", "technician"):
                headers = auth_headers(
                    range_staff[role_key], tenant_id=tenant_a.schema_name
                )
                res = _post_range(client, lab_test.id, headers)
                assert res.status_code == 403
                body = res.json()
                assert body["error"]["code"] == "forbidden"

    def test_create_range_validation_422(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """Field-level violations -> 422 validation_error with error envelope."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)

            bad_payloads = [
                _range_payload(low="18.000", high="17.500"),  # low > high
                _range_payload(critical_low="21.000", critical_high="20.000"),
                _range_payload(age_min_days=400, age_max_days=365),  # band inverted
                _range_payload(age_min_days=-1),  # negative age
                _range_payload(sex="X"),  # invalid sex
                _range_payload(unit=""),  # blank unit
                _range_payload(
                    effective_from="2027-06-01", effective_to="2027-01-01"
                ),  # window inverted
                _range_payload(evil_field="x"),  # unknown field rejected
            ]
            # missing required field
            missing = _range_payload()
            del missing["sex"]
            bad_payloads.append(missing)

            for payload in bad_payloads:
                res = client.post(
                    f"/api/v1/tests/{lab_test.id}/ranges",
                    data=payload,
                    content_type="application/json",
                    **headers,
                )
                assert res.status_code == 422, payload
                body = res.json()
                assert "error" in body
                assert body["error"]["code"] == "validation_error"


@pytest.mark.django_db
class TestReferenceRangeOverlap:
    def test_overlap_same_bucket_rejected_422(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """CT-4/CT-V2: overlapping same-bucket range -> 422 overlapping_range."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            first = _post_range(client, lab_test.id, headers)
            assert first.status_code == 201

            # Same sex, overlapping age band, overlapping effective window
            second = _post_range(
                client,
                lab_test.id,
                headers,
                age_min_days=100,
                age_max_days=200,
                effective_from="2027-06-01",
            )
            assert second.status_code == 422
            assert second.json()["error"]["code"] == "overlapping_range"

    def test_overlap_b_sex_rejected(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """B overlaps M and F in both directions."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            assert _post_range(client, lab_test.id, headers, sex="B").status_code == 201

            # Incoming M overlaps existing B
            res = _post_range(client, lab_test.id, headers, sex="M")
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "overlapping_range"

    def test_no_overlap_disjoint_dimensions_ok(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """Disjoint age band / sex / effective window -> 201."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            assert _post_range(client, lab_test.id, headers).status_code == 201

            # Disjoint age band
            r2 = _post_range(
                client, lab_test.id, headers, age_min_days=366, age_max_days=730
            )
            assert r2.status_code == 201

            # Disjoint sex
            r3 = _post_range(client, lab_test.id, headers, sex="F")
            assert r3.status_code == 201

            # Disjoint effective window (existing is open-ended from 2026-01-01;
            # retire it first via PATCH, then a later window is allowed)
            first_id = _post_range(
                client,
                lab_test.id,
                headers,
                sex="F",
                age_min_days=800,
                age_max_days=None,
            ).json()["id"]
            retire = client.patch(
                f"/api/v1/tests/{lab_test.id}/ranges/{first_id}",
                data={"effective_to": "2027-12-31"},
                content_type="application/json",
                **headers,
            )
            assert retire.status_code == 200
            r4 = _post_range(
                client,
                lab_test.id,
                headers,
                sex="F",
                age_min_days=800,
                age_max_days=None,
                effective_from="2028-01-01",
            )
            assert r4.status_code == 201

    def test_touching_age_boundary_counts_as_overlap(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """Bands sharing a boundary day overlap (deterministic rule)."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            assert _post_range(client, lab_test.id, headers).status_code == 201
            res = _post_range(
                client, lab_test.id, headers, age_min_days=365, age_max_days=730
            )
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "overlapping_range"


@pytest.mark.django_db
class TestReferenceRangePatch:
    def test_patch_supersedes_and_preserves_history(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """PATCH closes the old row and opens a new one; history preserved."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            created = _post_range(client, lab_test.id, headers)
            old_id = created.json()["id"]

            res = client.patch(
                f"/api/v1/tests/{lab_test.id}/ranges/{old_id}",
                data={"high": "18.000", "effective_from": "2027-06-01"},
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 200
            new_data = res.json()
            assert new_data["id"] != old_id
            assert new_data["high"] == "18.000"
            assert new_data["effective_from"] == "2027-06-01"

            # Old row preserved with closure date
            old_row = ReferenceRange.objects.get(id=old_id)
            assert old_row.effective_to == date(2027, 5, 31)
            assert old_row.high == Decimal("17.500")

            # Audit row for the supersede
            audit = AuditLog.objects.filter(
                action="catalog.range_updated",
                entity_id=uuid.UUID(new_data["id"]),
            ).first()
            assert audit is not None
            assert audit.before_jsonb is not None
            assert audit.after_jsonb is not None
            assert audit.before_jsonb["high"] == "17.500"
            assert audit.after_jsonb["high"] == "18.000"

    def test_patch_pathologist_200_and_others_403(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        with tenant_context(tenant_a):
            owner_headers = auth_headers(
                range_staff["owner"], tenant_id=tenant_a.schema_name
            )
            created = _post_range(
                client,
                lab_test.id,
                owner_headers,
                sex="F",
                age_min_days=500,
                age_max_days=None,
            )
            range_id = created.json()["id"]

            path_headers = auth_headers(
                range_staff["pathologist"], tenant_id=tenant_a.schema_name
            )
            ok = client.patch(
                f"/api/v1/tests/{lab_test.id}/ranges/{range_id}",
                data={"unit": "g/L", "effective_from": "2027-06-01"},
                content_type="application/json",
                **path_headers,
            )
            assert ok.status_code == 200

            for role_key in ("manager", "receptionist", "technician"):
                headers = auth_headers(
                    range_staff[role_key], tenant_id=tenant_a.schema_name
                )
                res = client.patch(
                    f"/api/v1/tests/{lab_test.id}/ranges/{range_id}",
                    data={"unit": "g/L"},
                    content_type="application/json",
                    **headers,
                )
                assert res.status_code == 403
                assert res.json()["error"]["code"] == "forbidden"

    def test_patch_retire_with_effective_to_only(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """PATCH with only effective_to closes the row without a successor."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            created = _post_range(
                client,
                lab_test.id,
                headers,
                sex="F",
                age_min_days=900,
                age_max_days=None,
            )
            range_id = created.json()["id"]

            res = client.patch(
                f"/api/v1/tests/{lab_test.id}/ranges/{range_id}",
                data={"effective_to": "2027-10-01"},
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 200
            assert res.json()["effective_to"] == "2027-10-01"
            assert ReferenceRange.objects.count() == 1

    def test_patch_invalid_effective_window_422(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """New effective_from before the row's start cannot rewrite history."""
        with tenant_context(tenant_a):
            headers = auth_headers(range_staff["owner"], tenant_id=tenant_a.schema_name)
            created = _post_range(client, lab_test.id, headers)
            range_id = created.json()["id"]

            res = client.patch(
                f"/api/v1/tests/{lab_test.id}/ranges/{range_id}",
                data={"effective_from": "2025-01-01"},
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "invalid_effective_window"


@pytest.mark.django_db
class TestResolveReferenceRange:
    def _seed(
        self,
        lab_test: Test,
        owner: StaffUser,
        **overrides: Any,
    ) -> ReferenceRange:
        params: dict[str, Any] = {
            "sex": "M",
            "age_min_days": 0,
            "age_max_days": 365,
            "low": Decimal("13.500"),
            "high": Decimal("17.500"),
            "critical_low": Decimal("7.000"),
            "critical_high": Decimal("20.000"),
            "unit": "g/dL",
            "effective_from": date(2026, 1, 1),
            "effective_to": None,
        }
        params.update(overrides)
        return CatalogService.create_reference_range(
            test_id=lab_test.id, actor=owner, **params
        )

    def _seed_direct(self, lab_test: Test, **overrides: Any) -> ReferenceRange:
        """Create a range row bypassing service validation.

        CT-4 overlap rejection means two rows that could both be selected for
        the same (sex, age, date) can never coexist via the service. Direct
        creation simulates legacy data so the §8.2 tie-breaks can be
        exercised in isolation.
        """
        params: dict[str, Any] = {
            "sex": "M",
            "age_min_days": 0,
            "age_max_days": 365,
            "low": Decimal("13.500"),
            "high": Decimal("17.500"),
            "critical_low": Decimal("7.000"),
            "critical_high": Decimal("20.000"),
            "unit": "g/dL",
            "effective_from": date(2026, 1, 1),
            "effective_to": None,
        }
        params.update(overrides)
        return ReferenceRange.objects.create(test=lab_test, **params)

    def test_t10_future_range_never_selected(
        self,
        tenant_a: Any,
        range_staff: dict[str, Any],
        lab_test: Test,
    ) -> None:
        """T-10: a range effective after collection is never selected."""
        with tenant_context(tenant_a):
            owner = range_staff["owner"]
            self._seed(lab_test, owner)
            self._seed(
                lab_test,
                owner,
                sex="M",
                age_min_days=400,
                age_max_days=800,
                effective_from=date(2026, 12, 1),  # future scheduled change
            )

            chosen = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex="M",
                patient_age_days=500,
                collection_date=date(2026, 6, 15),
            )
            assert chosen is None

            # After the future row becomes effective it is selected
            chosen_later = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex="M",
                patient_age_days=500,
                collection_date=date(2026, 12, 15),
            )
            assert chosen_later is not None
            assert chosen_later.age_min_days == 400

    def test_tiebreak_specific_sex_beats_b(
        self,
        tenant_a: Any,
        range_staff: dict[str, Any],
        lab_test: Test,
    ) -> None:
        """§8.2: specific sex (M) takes precedence over B (Both)."""
        with tenant_context(tenant_a):
            self._seed_direct(lab_test, sex="B")
            specific = self._seed_direct(lab_test, sex="M")

            chosen = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex="M",
                patient_age_days=100,
                collection_date=date(2026, 6, 15),
            )
            assert chosen is not None
            assert chosen.id == specific.id

    def test_tiebreak_narrower_band_beats_wider(
        self,
        tenant_a: Any,
        range_staff: dict[str, Any],
        lab_test: Test,
    ) -> None:
        """§8.2: narrower age band takes precedence over wider."""
        with tenant_context(tenant_a):
            self._seed_direct(lab_test, sex="M")  # 0..365
            narrow = self._seed_direct(
                lab_test, sex="M", age_min_days=50, age_max_days=150
            )

            chosen = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex="M",
                patient_age_days=100,
                collection_date=date(2026, 6, 15),
            )
            assert chosen is not None
            assert chosen.id == narrow.id

    def test_age_boundaries_inclusive_and_open_ended(
        self,
        tenant_a: Any,
        range_staff: dict[str, Any],
        lab_test: Test,
    ) -> None:
        with tenant_context(tenant_a):
            owner = range_staff["owner"]
            open_ended = self._seed(
                lab_test, owner, sex="M", age_min_days=365, age_max_days=None
            )

            for age in (365, 1000, 36500):
                chosen = CatalogService.resolve_reference_range(
                    test_id=lab_test.id,
                    patient_sex="M",
                    patient_age_days=age,
                    collection_date=date(2026, 6, 15),
                )
                assert chosen is not None
                assert chosen.id == open_ended.id

    def test_unknown_sex_falls_back_to_b(
        self,
        tenant_a: Any,
        range_staff: dict[str, Any],
        lab_test: Test,
    ) -> None:
        with tenant_context(tenant_a):
            owner = range_staff["owner"]
            both = self._seed(lab_test, owner, sex="B")
            self._seed(lab_test, owner, sex="M", age_min_days=400, age_max_days=None)

            chosen = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex=None,
                patient_age_days=100,
                collection_date=date(2026, 6, 15),
            )
            assert chosen is not None
            assert chosen.id == both.id

    def test_no_match_returns_none(
        self,
        tenant_a: Any,
        range_staff: dict[str, Any],
        lab_test: Test,
    ) -> None:
        with tenant_context(tenant_a):
            owner = range_staff["owner"]
            self._seed(lab_test, owner, sex="F")

            chosen = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex="M",
                patient_age_days=100,
                collection_date=date(2026, 6, 15),
            )
            assert chosen is None

    def test_selection_is_deterministic(
        self,
        tenant_a: Any,
        range_staff: dict[str, Any],
        lab_test: Test,
    ) -> None:
        with tenant_context(tenant_a):
            self._seed_direct(lab_test, sex="B")
            self._seed_direct(lab_test, sex="M")

            first = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex="M",
                patient_age_days=100,
                collection_date=date(2026, 6, 15),
            )
            second = CatalogService.resolve_reference_range(
                test_id=lab_test.id,
                patient_sex="M",
                patient_age_days=100,
                collection_date=date(2026, 6, 15),
            )
            assert first is not None and second is not None
            assert first.id == second.id


@pytest.mark.django_db
class TestReferenceRangeErrorEnvelope:
    def test_all_errors_use_envelope(
        self,
        client: Client,
        tenant_a: Any,
        range_staff: dict[str, Any],
        auth_headers: Any,
        lab_test: Test,
    ) -> None:
        """Doc 08: every error response matches the standard envelope."""
        with tenant_context(tenant_a):
            manager_headers = auth_headers(
                range_staff["manager"], tenant_id=tenant_a.schema_name
            )
            owner_headers = auth_headers(
                range_staff["owner"], tenant_id=tenant_a.schema_name
            )

            res_403 = _post_range(client, lab_test.id, manager_headers)
            assert res_403.status_code == 403

            res_422 = client.post(
                f"/api/v1/tests/{lab_test.id}/ranges",
                data=_range_payload(low="99.000", high="1.000"),
                content_type="application/json",
                **owner_headers,
            )
            assert res_422.status_code == 422

            for res in (res_403, res_422):
                body = res.json()
                assert set(body.keys()) == {"error"}
                assert "code" in body["error"]
                assert "message" in body["error"]
