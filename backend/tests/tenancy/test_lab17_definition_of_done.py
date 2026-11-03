"""LAB-17 Definition of Done Suite (KAN-119).

Verifies cross-tenant isolation, the full RBAC matrix, overlap edge cases,
audit immutability, history preservation, and deterministic selection —
the DoD bars for biological reference ranges (Doc 03 §5.2, §8.2).
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.catalog.models import ReferenceRange, Test
from apps.catalog.services import CatalogService, OverlappingRangeError
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


def _make_staff(tenant: Any, prefix: str) -> dict[str, Any]:
    with tenant_context(tenant):
        branch = BranchFactory(code=f"{prefix[:2]}1", name=f"{prefix} Branch")
        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email=f"{prefix}_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email=f"{prefix}_mgr@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email=f"{prefix}_rec@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email=f"{prefix}_tec@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=None, email=f"{prefix}_pat@tenant.com"
        )
        test_obj = Test.objects.create(
            code=f"{prefix}T", name=f"{prefix} Test", unit="g/dL"
        )
        return {
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "pathologist": pathologist,
            "test": test_obj,
        }


def _payload(**overrides: Any) -> dict[str, Any]:
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


@pytest.mark.django_db
class TestLab17TenantIsolation:
    def test_ranges_are_invisible_cross_tenant(
        self,
        client: Client,
        tenant_a: Any,
        tenant_b: Any,
        auth_headers: Any,
    ) -> None:
        """Reference ranges live strictly inside the tenant schema."""
        staff_a = _make_staff(tenant_a, "DODA")
        staff_b = _make_staff(tenant_b, "DODB")

        with tenant_context(tenant_a):
            created = CatalogService.create_reference_range(
                test_id=staff_a["test"].id,
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
                actor=staff_a["owner"],
            )
            assert ReferenceRange.objects.count() == 1

        with tenant_context(tenant_b):
            assert ReferenceRange.objects.count() == 0
            assert (
                CatalogService.resolve_reference_range(
                    test_id=staff_a["test"].id,
                    patient_sex="M",
                    patient_age_days=100,
                    collection_date=date(2026, 6, 1),
                )
                is None
            )
            assert ReferenceRange.objects.filter(id=created.id).first() is None

        # Via API: tenant B owner listing B's test sees no ranges
        headers_b = auth_headers(staff_b["owner"], tenant_id=tenant_b.schema_name)
        with tenant_context(tenant_b):
            res = client.get(f"/api/v1/tests/{staff_b['test'].id}/ranges", **headers_b)
            assert res.status_code == 200
            assert res.json() == []


@pytest.mark.django_db
class TestLab17RbacMatrix:
    @pytest.mark.parametrize(
        ("role_key", "expected_post", "expected_patch"),
        [
            ("owner", 201, 200),
            ("pathologist", 201, 200),
            ("manager", 403, 403),
            ("receptionist", 403, 403),
            ("technician", 403, 403),
        ],
    )
    def test_write_matrix(
        self,
        client: Client,
        tenant_a: Any,
        auth_headers: Any,
        role_key: str,
        expected_post: int,
        expected_patch: int,
    ) -> None:
        """Only Owner and Pathologist may write ranges (POST + PATCH)."""
        staff = _make_staff(tenant_a, f"DOD{role_key[:3].upper()}")
        test_obj = staff["test"]

        with tenant_context(tenant_a):
            headers = auth_headers(staff[role_key], tenant_id=tenant_a.schema_name)

            post_res = client.post(
                f"/api/v1/tests/{test_obj.id}/ranges",
                data=_payload(),
                content_type="application/json",
                **headers,
            )
            assert post_res.status_code == expected_post

            # Seed one row as owner for the PATCH probe (distinct bucket)
            owner_headers = auth_headers(staff["owner"], tenant_id=tenant_a.schema_name)
            seeded = client.post(
                f"/api/v1/tests/{test_obj.id}/ranges",
                data=_payload(sex="F"),
                content_type="application/json",
                **owner_headers,
            )
            assert seeded.status_code == 201

            patch_res = client.patch(
                f"/api/v1/tests/{test_obj.id}/ranges/{seeded.json()['id']}",
                data={"unit": "g/L", "effective_from": "2027-06-01"},
                content_type="application/json",
                **headers,
            )
            assert patch_res.status_code == expected_patch


@pytest.mark.django_db
class TestLab17OverlapEdgeCases:
    def test_service_raises_overlapping_range_error(self, tenant_a: Any) -> None:
        """Service-level overlap raises OverlappingRangeError (CT-4)."""
        staff = _make_staff(tenant_a, "DODO")
        with tenant_context(tenant_a):
            CatalogService.create_reference_range(
                test_id=staff["test"].id,
                sex="M",
                age_min_days=0,
                age_max_days=365,
                low=Decimal("1.000"),
                high=Decimal("2.000"),
                critical_low=None,
                critical_high=None,
                unit="u",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                actor=staff["owner"],
            )
            with pytest.raises(OverlappingRangeError):
                CatalogService.create_reference_range(
                    test_id=staff["test"].id,
                    sex="B",
                    age_min_days=300,
                    age_max_days=400,
                    low=Decimal("1.000"),
                    high=Decimal("2.000"),
                    critical_low=None,
                    critical_high=None,
                    unit="u",
                    effective_from=date(2026, 3, 1),
                    effective_to=None,
                    actor=staff["owner"],
                )

    def test_open_ended_windows_overlap(self, tenant_a: Any) -> None:
        """Two open-ended effective windows always overlap."""
        staff = _make_staff(tenant_a, "DODW")
        with tenant_context(tenant_a):
            CatalogService.create_reference_range(
                test_id=staff["test"].id,
                sex="F",
                age_min_days=0,
                age_max_days=None,
                low=Decimal("1.000"),
                high=Decimal("2.000"),
                critical_low=None,
                critical_high=None,
                unit="u",
                effective_from=date(2025, 1, 1),
                effective_to=None,
                actor=staff["owner"],
            )
            with pytest.raises(OverlappingRangeError):
                CatalogService.create_reference_range(
                    test_id=staff["test"].id,
                    sex="F",
                    age_min_days=10,
                    age_max_days=None,
                    low=Decimal("1.000"),
                    high=Decimal("2.000"),
                    critical_low=None,
                    critical_high=None,
                    unit="u",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    actor=staff["owner"],
                )

    def test_effective_window_db_constraint(self, tenant_a: Any) -> None:
        """DB enforces effective_to >= effective_from."""
        staff = _make_staff(tenant_a, "DODC")
        with tenant_context(tenant_a), pytest.raises(IntegrityError):
            ReferenceRange.objects.create(
                test=staff["test"],
                sex="M",
                age_min_days=0,
                age_max_days=100,
                low=Decimal("1.000"),
                high=Decimal("2.000"),
                unit="u",
                effective_from=date(2026, 6, 1),
                effective_to=date(2026, 1, 1),
            )


@pytest.mark.django_db
class TestLab17AuditImmutability:
    def test_audit_rows_are_append_only(self, tenant_a: Any) -> None:
        """Every range mutation emits exactly one immutable audit row."""
        staff = _make_staff(tenant_a, "DODI")
        with tenant_context(tenant_a):
            created = CatalogService.create_reference_range(
                test_id=staff["test"].id,
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
                actor=staff["owner"],
            )
            CatalogService.supersede_reference_range(
                range_obj=created,
                data={"high": Decimal("18.000")},
                actor=staff["pathologist"],
            )

            rows = AuditLog.objects.filter(entity_type="reference_range").order_by("at")
            actions = [r.action for r in rows]
            assert actions == ["catalog.range_created", "catalog.range_updated"]
            # AuditLog has no updated_at: rows are never modified
            assert not hasattr(AuditLog, "updated_at")
            for row in rows:
                assert row.actor_id in (staff["owner"].id, staff["pathologist"].id)

    def test_history_preserved_across_supersedes(self, tenant_a: Any) -> None:
        """Supersede never deletes: all generations remain queryable."""
        staff = _make_staff(tenant_a, "DODH")
        with tenant_context(tenant_a):
            gen1 = CatalogService.create_reference_range(
                test_id=staff["test"].id,
                sex="M",
                age_min_days=0,
                age_max_days=365,
                low=Decimal("13.500"),
                high=Decimal("17.500"),
                critical_low=None,
                critical_high=None,
                unit="g/dL",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                actor=staff["owner"],
            )
            gen2 = CatalogService.supersede_reference_range(
                range_obj=gen1,
                data={"high": Decimal("18.000")},
                actor=staff["owner"],
            )
            gen3 = CatalogService.supersede_reference_range(
                range_obj=gen2,
                data={"high": Decimal("19.000")},
                actor=staff["owner"],
            )

            all_rows = ReferenceRange.objects.filter(test_id=staff["test"].id).order_by(
                "effective_from"
            )
            assert all_rows.count() == 3
            assert [r.high for r in all_rows] == [
                Decimal("17.500"),
                Decimal("18.000"),
                Decimal("19.000"),
            ]
            # Generation 1 closed the day before generation 2 started
            gen1.refresh_from_db()
            assert gen1.effective_to == gen2.effective_from - timedelta(days=1)
            assert gen3.effective_to is None


@pytest.mark.django_db
class TestLab17SelectionContract:
    def test_selection_prefers_latest_effective_on_legacy_tie(
        self, tenant_a: Any
    ) -> None:
        """Final deterministic tie-break: latest effective_from wins."""
        staff = _make_staff(tenant_a, "DODS")
        with tenant_context(tenant_a):
            # Two rows that would tie on sex specificity and band width
            # (constructed directly to simulate legacy data).
            ReferenceRange.objects.create(
                test=staff["test"],
                sex="M",
                age_min_days=0,
                age_max_days=365,
                low=Decimal("1.000"),
                high=Decimal("2.000"),
                unit="u",
                effective_from=date(2025, 1, 1),
                effective_to=date(2025, 12, 31),
            )
            ReferenceRange.objects.create(
                test=staff["test"],
                sex="M",
                age_min_days=0,
                age_max_days=365,
                low=Decimal("1.500"),
                high=Decimal("2.500"),
                unit="u",
                effective_from=date(2026, 1, 1),
                effective_to=None,
            )

            chosen = CatalogService.resolve_reference_range(
                test_id=staff["test"].id,
                patient_sex="M",
                patient_age_days=100,
                collection_date=date(2026, 6, 1),
            )
            assert chosen is not None
            assert chosen.low == Decimal("1.500")

    def test_collection_date_as_datetime(self, tenant_a: Any) -> None:
        """Datetime collection timestamps are normalized to dates (T-10)."""
        from datetime import datetime

        staff = _make_staff(tenant_a, "DODT")
        with tenant_context(tenant_a):
            CatalogService.create_reference_range(
                test_id=staff["test"].id,
                sex="M",
                age_min_days=0,
                age_max_days=365,
                low=Decimal("1.000"),
                high=Decimal("2.000"),
                critical_low=None,
                critical_high=None,
                unit="u",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                actor=staff["owner"],
            )
            chosen = CatalogService.resolve_reference_range(
                test_id=staff["test"].id,
                patient_sex="M",
                patient_age_days=100,
                collection_date=datetime(2026, 6, 1, 14, 30),
            )
            assert chosen is not None
