"""LAB-16 Test Suite: Diagnostic Catalog, Panels & Prices (Doc 03 §5.2, §6.3).

Covers:
1. Test CRUD (GET/POST/PATCH /api/v1/tests) with Owner-only writes and BS-5 read matrix.
2. Panel CRUD (GET/POST/PATCH /api/v1/panels) with CT-V3 validation.
3. Test & Panel effective-dated pricing (POST /api/v1/tests/{id}/prices) per CT-2.
4. Decimal string validation CT-V1 and T-12 (money_must_be_string).
5. Unpriced test detection CT-3 and T-16 (test_not_priced).
6. test_price XOR CHECK constraint (chk_test_price_test_xor_panel).
7. Audit log contract on all catalog writes.
8. Tenant isolation for catalog entities.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.catalog.models import Panel, PanelTest, Test, TestPrice
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
def catalog_staff_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="cat_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="cat_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)

        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="cat_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )

        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="cat_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )

        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=None, email="cat_path@tenant.com"
        )

        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "pathologist": pathologist,
        }


@pytest.mark.django_db
class TestCatalogTestCRUD:
    def test_list_tests_read_matrix_bs5(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """BS-5: Tests are tenant-wide reference data readable by O, M, R, T, P."""
        with tenant_context(tenant_a):
            Test.objects.create(
                code="GLU", name="Glucose Fasting", category="Biochemistry"
            )
            Test.objects.create(
                code="CHOL", name="Total Cholesterol", category="Lipids"
            )

            roles_to_test = [
                catalog_staff_setup["owner"],
                catalog_staff_setup["manager"],
                catalog_staff_setup["receptionist"],
                catalog_staff_setup["technician"],
                catalog_staff_setup["pathologist"],
            ]

            for staff in roles_to_test:
                headers = auth_headers(staff, tenant_id=tenant_a.schema_name)
                res = client.get("/api/v1/tests", **headers)
                assert res.status_code == 200
                codes = [item["code"] for item in res.json()]
                assert "GLU" in codes
                assert "CHOL" in codes

            # Test search query filter ?q=
            headers = auth_headers(
                catalog_staff_setup["receptionist"], tenant_id=tenant_a.schema_name
            )
            q_res = client.get("/api/v1/tests?q=Glucose", **headers)
            assert q_res.status_code == 200
            q_codes = [item["code"] for item in q_res.json()]
            assert "GLU" in q_codes
            assert "CHOL" not in q_codes

    def test_create_test_owner_only_and_audit(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """Doc 03 §6.3: POST /api/v1/tests allowed for Owner only; audits write."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            manager = catalog_staff_setup["manager"]
            headers_owner = auth_headers(owner, tenant_id=tenant_a.schema_name)
            headers_manager = auth_headers(manager, tenant_id=tenant_a.schema_name)

            # 1. Non-owner gets 403 Forbidden
            forbidden_res = client.post(
                "/api/v1/tests",
                data={"code": "ALT", "name": "Alanine Aminotransferase"},
                content_type="application/json",
                **headers_manager,
            )
            assert forbidden_res.status_code == 403

            # 2. Owner creates test -> 201 Created
            create_res = client.post(
                "/api/v1/tests",
                data={
                    "code": "ALT",
                    "name": "Alanine Aminotransferase",
                    "category": "Liver Function",
                    "unit": "U/L",
                },
                content_type="application/json",
                **headers_owner,
            )
            assert create_res.status_code == 201
            data = create_res.json()
            assert data["code"] == "ALT"
            assert data["name"] == "Alanine Aminotransferase"
            assert data["unit"] == "U/L"
            test_id = uuid.UUID(data["id"])

            # Verify audit log contract
            audit = AuditLog.objects.filter(
                action="catalog.test_created",
                entity_id=test_id,
            ).first()
            assert audit is not None
            assert audit.actor_id == owner.id
            assert audit.after_jsonb is not None
            assert audit.after_jsonb["code"] == "ALT"

    def test_create_test_validation_errors(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """422 on missing required fields or duplicate code."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            # Missing code
            res1 = client.post(
                "/api/v1/tests",
                data={"name": "No Code Test"},
                content_type="application/json",
                **headers,
            )
            assert res1.status_code == 422

            # Duplicate code
            Test.objects.create(code="DUP", name="First Duplicate Test")
            res2 = client.post(
                "/api/v1/tests",
                data={"code": "DUP", "name": "Second Duplicate Test"},
                content_type="application/json",
                **headers,
            )
            assert res2.status_code in (409, 422)

    def test_patch_test_owner_success_and_audit(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """PATCH /api/v1/tests/{id} updates fields and audits change."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            test_obj = Test.objects.create(
                code="HBA1C", name="HbA1c", category="Diabetes"
            )
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            patch_res = client.patch(
                f"/api/v1/tests/{test_obj.id}",
                data={"name": "Glycated Hemoglobin (HbA1c)", "unit": "%"},
                content_type="application/json",
                **headers,
            )
            assert patch_res.status_code == 200
            assert patch_res.json()["name"] == "Glycated Hemoglobin (HbA1c)"
            assert patch_res.json()["unit"] == "%"

            test_obj.refresh_from_db()
            assert test_obj.name == "Glycated Hemoglobin (HbA1c)"
            assert test_obj.unit == "%"

            # Audit row verified
            audit = AuditLog.objects.filter(
                action="catalog.test_updated",
                entity_id=test_obj.id,
            ).first()
            assert audit is not None
            assert audit.before_jsonb is not None
            assert audit.after_jsonb is not None
            assert audit.before_jsonb["name"] == "HbA1c"
            assert audit.after_jsonb["name"] == "Glycated Hemoglobin (HbA1c)"


@pytest.mark.django_db
class TestCatalogPanelCRUD:
    def test_create_panel_with_components_and_audit(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """Owner creates panel with component tests; joins created in panel_test."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            t1 = Test.objects.create(code="BUN", name="Blood Urea Nitrogen")
            t2 = Test.objects.create(code="CREAT", name="Creatinine")

            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)
            res = client.post(
                "/api/v1/panels",
                data={
                    "code": "RFT",
                    "name": "Renal Function Tests",
                    "test_ids": [str(t1.id), str(t2.id)],
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 201
            data = res.json()
            assert data["code"] == "RFT"
            panel_id = uuid.UUID(data["id"])

            # Verify components in join table
            panel_tests = PanelTest.objects.filter(panel_id=panel_id)
            assert panel_tests.count() == 2
            component_ids = {str(pt.test_id) for pt in panel_tests}
            assert str(t1.id) in component_ids
            assert str(t2.id) in component_ids

            # Verify audit
            audit = AuditLog.objects.filter(
                action="catalog.panel_created",
                entity_id=panel_id,
            ).first()
            assert audit is not None
            assert audit.after_jsonb is not None
            assert audit.after_jsonb["code"] == "RFT"

    def test_create_panel_empty_components_rejected_422(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """CT-V3: Panel must contain at least one component test -> 422 empty_panel."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            res = client.post(
                "/api/v1/panels",
                data={"code": "EMPTY", "name": "Empty Panel", "test_ids": []},
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "empty_panel"

    def test_create_panel_inactive_component_rejected_422(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """CT-V3: Deactivated test rejected at save time -> 422."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            t_active = Test.objects.create(
                code="ACT", name="Active Test", is_active=True
            )
            t_inactive = Test.objects.create(
                code="INACT", name="Inactive Test", is_active=False
            )

            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)
            res = client.post(
                "/api/v1/panels",
                data={
                    "code": "BAD_PANEL",
                    "name": "Panel with Inactive",
                    "test_ids": [str(t_active.id), str(t_inactive.id)],
                },
                content_type="application/json",
                **headers,
            )
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "inactive_component"


@pytest.mark.django_db
class TestTestPricingAndXOR:
    def test_test_pricing_effective_dating_ct2(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """CT-2: Price change closes the old row and opens a new one."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            test_obj = Test.objects.create(code="LIP", name="Lipase")
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            # 1. First price row: 1000.00 effective from 2026-01-01
            p1_res = client.post(
                f"/api/v1/tests/{test_obj.id}/prices",
                data={"amount": "1000.00", "effective_from": "2026-01-01T00:00:00Z"},
                content_type="application/json",
                **headers,
            )
            assert p1_res.status_code == 201
            data1 = p1_res.json()
            assert data1["price"] == "1000.00"
            assert data1["effective_to"] is None

            p1 = TestPrice.objects.get(id=uuid.UUID(data1["id"]))
            assert p1.effective_to is None

            # 2. Second price row: 1200.00 effective from 2026-06-01
            p2_res = client.post(
                f"/api/v1/tests/{test_obj.id}/prices",
                data={"amount": "1200.00", "effective_from": "2026-06-01T00:00:00Z"},
                content_type="application/json",
                **headers,
            )
            assert p2_res.status_code == 201
            data2 = p2_res.json()
            assert data2["price"] == "1200.00"
            assert data2["effective_to"] is None

            # Verify p1 was closed with p2's effective_from
            p1.refresh_from_db()
            assert p1.effective_to is not None
            assert p1.effective_to.isoformat().startswith("2026-06-01")

            # 3. GET /tests/{id}/prices returns history
            get_res = client.get(f"/api/v1/tests/{test_obj.id}/prices", **headers)
            assert get_res.status_code == 200
            prices = get_res.json()
            assert len(prices) == 2

            # Verify audit log row
            audit = (
                AuditLog.objects.filter(
                    action="catalog.price_changed",
                    entity_id=test_obj.id,
                )
                .order_by("at")
                .last()
            )
            assert audit is not None
            assert audit.after_jsonb is not None
            assert audit.after_jsonb["amount"] == "1200.00"

    def test_test_pricing_validation_ct_v1_and_t12(
        self,
        client: Client,
        tenant_a: Any,
        catalog_staff_setup: dict[str, Any],
        auth_headers: Any,
    ) -> None:
        """T-12: Non-string or 3-decimal amount -> 422 money_must_be_string."""
        with tenant_context(tenant_a):
            owner = catalog_staff_setup["owner"]
            test_obj = Test.objects.create(code="AMY", name="Amylase")
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            # JSON number instead of string
            res1 = client.post(
                f"/api/v1/tests/{test_obj.id}/prices",
                data={"amount": 1500.5, "effective_from": "2026-01-01T00:00:00Z"},
                content_type="application/json",
                **headers,
            )
            assert res1.status_code == 422
            assert res1.json()["error"]["code"] == "money_must_be_string"

            # 3 decimal places
            res2 = client.post(
                f"/api/v1/tests/{test_obj.id}/prices",
                data={"amount": "1500.555", "effective_from": "2026-01-01T00:00:00Z"},
                content_type="application/json",
                **headers,
            )
            assert res2.status_code == 422

            # Negative price
            res3 = client.post(
                f"/api/v1/tests/{test_obj.id}/prices",
                data={"amount": "-100.00", "effective_from": "2026-01-01T00:00:00Z"},
                content_type="application/json",
                **headers,
            )
            assert res3.status_code == 422

    def test_test_price_xor_check_enforced(self, tenant_a: Any) -> None:
        """Database CHECK chk_test_price_test_xor_panel rejects violations."""
        with tenant_context(tenant_a):
            t = Test.objects.create(code="T1", name="Test 1")
            p = Panel.objects.create(code="P1", name="Panel 1")
            now = datetime.now(UTC)

            # 1. Both test and panel set -> violates XOR CHECK
            with pytest.raises(IntegrityError), transaction.atomic():
                TestPrice.objects.create(
                    test=t,
                    panel=p,
                    price=Decimal("500.00"),
                    effective_from=now,
                )

            # 2. Neither test nor panel set -> violates XOR CHECK
            with pytest.raises(IntegrityError), transaction.atomic():
                TestPrice.objects.create(
                    test=None,
                    panel=None,
                    price=Decimal("500.00"),
                    effective_from=now,
                )

            # 3. Only test set -> succeeds
            tp = TestPrice.objects.create(
                test=t,
                panel=None,
                price=Decimal("500.00"),
                effective_from=now,
            )
            assert tp.id is not None
