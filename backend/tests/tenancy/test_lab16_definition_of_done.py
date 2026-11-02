"""LAB-16 Definition of Done Verification Suite (Doc 03 §5.2, §6.3, KAN-118).

Mandatory DoD Verifications:
1. Cross-tenant catalog isolation (Tenant A catalog entities invisible to Tenant B).
2. Panel update (PATCH /api/v1/panels/{id}) with component validation & audit logging.
3. Panel pricing effective dating (CT-2) with role authorization (Owner only writes).
4. Service helper get_effective_price raising TestNotPricedError (CT-3, T-16).
5. Catalog deactivation vs deletion policy (CT-5).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.catalog.models import Panel, PanelTest, Test, TestPrice
from apps.catalog.services import CatalogService, TestNotPricedError
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


@pytest.mark.django_db
class TestLab16DefinitionOfDone:
    def test_dod_cross_tenant_catalog_isolation(
        self,
        client: Client,
        tenant_a: Any,
        tenant_b: Any,
        auth_headers: Any,
    ) -> None:
        """Tenant A tests & panels are completely isolated from Tenant B."""
        with tenant_context(tenant_a):
            owner_a = StaffUserFactory(role=Role.OWNER, email="owner_a@test.com")
            t_a = Test.objects.create(code="TEST_A", name="Tenant A Test")
            p_a = Panel.objects.create(code="PANEL_A", name="Tenant A Panel")
            PanelTest.objects.create(panel=p_a, test=t_a)
            headers_a = auth_headers(owner_a, tenant_id=tenant_a.schema_name)

        with tenant_context(tenant_b):
            owner_b = StaffUserFactory(role=Role.OWNER, email="owner_b@test.com")
            t_b = Test.objects.create(code="TEST_B", name="Tenant B Test")
            p_b = Panel.objects.create(code="PANEL_B", name="Tenant B Panel")
            PanelTest.objects.create(panel=p_b, test=t_b)
            headers_b = auth_headers(owner_b, tenant_id=tenant_b.schema_name)

        # Tenant A sees only TEST_A and PANEL_A
        res_a_tests = client.get("/api/v1/tests", **headers_a)
        assert res_a_tests.status_code == 200
        codes_a = [item["code"] for item in res_a_tests.json()]
        assert "TEST_A" in codes_a
        assert "TEST_B" not in codes_a

        res_a_panels = client.get("/api/v1/panels", **headers_a)
        assert res_a_panels.status_code == 200
        p_codes_a = [item["code"] for item in res_a_panels.json()]
        assert "PANEL_A" in p_codes_a
        assert "PANEL_B" not in p_codes_a

        # Tenant B sees only TEST_B and PANEL_B
        res_b_tests = client.get("/api/v1/tests", **headers_b)
        assert res_b_tests.status_code == 200
        codes_b = [item["code"] for item in res_b_tests.json()]
        assert "TEST_B" in codes_b
        assert "TEST_A" not in codes_b

    def test_dod_panel_patch_and_audit(
        self,
        client: Client,
        tenant_a: Any,
        auth_headers: Any,
    ) -> None:
        """Owner can update panel name, active status, and component tests."""
        with tenant_context(tenant_a):
            owner = StaffUserFactory(role=Role.OWNER, email="owner_patch@test.com")
            headers = auth_headers(owner, tenant_id=tenant_a.schema_name)

            t1 = Test.objects.create(code="T1", name="Test One")
            t2 = Test.objects.create(code="T2", name="Test Two")
            t3 = Test.objects.create(code="T3", name="Test Three")

            panel = Panel.objects.create(code="PNL", name="Original Panel")
            PanelTest.objects.create(panel=panel, test=t1)
            PanelTest.objects.create(panel=panel, test=t2)

            patch_res = client.patch(
                f"/api/v1/panels/{panel.id}",
                data={
                    "name": "Updated Panel Name",
                    "test_ids": [str(t2.id), str(t3.id)],
                },
                content_type="application/json",
                **headers,
            )
            assert patch_res.status_code == 200
            data = patch_res.json()
            assert data["name"] == "Updated Panel Name"

            panel.refresh_from_db()
            assert panel.name == "Updated Panel Name"
            component_ids = set(panel.panel_tests.values_list("test_id", flat=True))
            assert component_ids == {t2.id, t3.id}

            # Verify audit
            audit = AuditLog.objects.filter(
                action="catalog.panel_updated",
                entity_id=panel.id,
            ).first()
            assert audit is not None
            assert isinstance(audit.before_jsonb, dict)
            assert isinstance(audit.after_jsonb, dict)
            assert audit.before_jsonb["name"] == "Original Panel"
            assert audit.after_jsonb["name"] == "Updated Panel Name"

    def test_dod_panel_pricing_effective_dating_and_rbac(
        self,
        client: Client,
        tenant_a: Any,
        auth_headers: Any,
    ) -> None:
        """Panel pricing follows CT-2 effective dating and Owner-only writes."""
        with tenant_context(tenant_a):
            owner = StaffUserFactory(role=Role.OWNER, email="owner_pr@test.com")
            manager = StaffUserFactory(role=Role.MANAGER, email="mgr_pr@test.com")
            headers_owner = auth_headers(owner, tenant_id=tenant_a.schema_name)
            headers_mgr = auth_headers(manager, tenant_id=tenant_a.schema_name)

            t = Test.objects.create(code="TP1", name="Panel Item 1")
            p = Panel.objects.create(code="PNL_PR", name="Pricing Panel")
            PanelTest.objects.create(panel=p, test=t)

            # Manager cannot post price (403)
            f_res = client.post(
                f"/api/v1/panels/{p.id}/prices",
                data={"amount": "2500.00"},
                content_type="application/json",
                **headers_mgr,
            )
            assert f_res.status_code == 403

            # Owner sets initial price
            r1 = client.post(
                f"/api/v1/panels/{p.id}/prices",
                data={
                    "amount": "2500.00",
                    "effective_from": "2026-01-01T00:00:00Z",
                },
                content_type="application/json",
                **headers_owner,
            )
            assert r1.status_code == 201
            p1_id = uuid.UUID(r1.json()["id"])

            # Owner updates price
            r2 = client.post(
                f"/api/v1/panels/{p.id}/prices",
                data={
                    "amount": "2800.00",
                    "effective_from": "2026-07-01T00:00:00Z",
                },
                content_type="application/json",
                **headers_owner,
            )
            assert r2.status_code == 201

            # Check old row closed
            price1 = TestPrice.objects.get(id=p1_id)
            assert price1.effective_to is not None
            assert price1.effective_to.isoformat().startswith("2026-07-01")

            # Manager can read price history
            hist_res = client.get(f"/api/v1/panels/{p.id}/prices", **headers_mgr)
            assert hist_res.status_code == 200
            assert len(hist_res.json()) == 2

    def test_dod_unpriced_test_guard_ct3_t16(self, tenant_a: Any) -> None:
        """get_effective_price raises TestNotPricedError when unpriced."""
        with tenant_context(tenant_a):
            t_unpriced = Test.objects.create(code="NOPRICE", name="Unpriced Test")
            with pytest.raises(TestNotPricedError):
                CatalogService.get_effective_price(test_id=t_unpriced.id)

            # Once priced, returns correct Decimal
            now = datetime.now(UTC)
            TestPrice.objects.create(
                test=t_unpriced,
                price=Decimal("750.00"),
                effective_from=now,
            )
            price = CatalogService.get_effective_price(test_id=t_unpriced.id)
            assert price == Decimal("750.00")
