"""LAB-18 Test Suite: Invoicing engine — invoice create (Doc 03 §5.3, §6.4, KAN-124).

Covers (original LAB-20):
- T-11: server computes totals in Decimal; client-sent totals ignored.
- T-13: Idempotency-Key required; replay → 200 original; reused key + new
  payload → 409 idempotency_key_reused.
- T-20: zero-total invoice → paid; discount RBAC (BL-3).
- BL-1: price snapshotting (description + unit_price at creation).
- BL-V1: money as Decimal strings (money_must_be_string).
- BL-V2: qty integer >= 1; duplicate same-kind lines merged.
- Audit: invoice.created row in the same transaction.
- Tenant scoping: out-of-scope patient/branch → 404, not 403.
"""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.models import Invoice, InvoiceItem
from apps.catalog.models import TestPrice
from tests.factories.branch import BranchFactory
from tests.factories.catalog import PanelFactory, TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

INVOICES_URL = "/api/v1/invoices"


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
            "Authorization": f"Bearer {session['access']}",
            "Host": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def billing_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="bill_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="bill_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="bill_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="bill_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )

        patient = PatientFactory(branch=branch)

        test_a = TestFactory(name="CBC Test", code="CBC001")
        TestPriceFactory(test=test_a, panel=None, price=Decimal("1500.00"))
        test_b = TestFactory(name="Lipid Test", code="LIP001")
        TestPriceFactory(test=test_b, panel=None, price=Decimal("800.00"))
        unpriced = TestFactory(name="Unpriced Test", code="NOP001")
        panel = PanelFactory(name="Basic Panel", code="PNL001")
        TestPriceFactory(test=None, panel=panel, price=Decimal("2500.00"))

        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "patient": patient,
            "test_a": test_a,
            "test_b": test_b,
            "unpriced": unpriced,
            "panel": panel,
        }


def _post_invoice(
    client: Client,
    headers: dict[str, str],
    body: dict[str, Any],
    idem_key: str | None = "idem-key-001",
) -> Any:
    extra = dict(headers)
    if idem_key is not None:
        extra["Idempotency-Key"] = idem_key
    import json

    return client.post(
        INVOICES_URL,
        data=json.dumps(body),
        content_type="application/json",
        headers=extra,
    )


def _base_body(setup: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "patient_id": str(setup["patient"].id),
        "branch_id": str(setup["branch"].id),
        "referral_partner_id": None,
        "items": [
            {"test_id": str(setup["test_a"].id), "qty": 1},
            {"test_id": str(setup["test_b"].id), "qty": 2},
        ],
        "discount_amount": "0.00",
        "discount_reason": None,
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
class TestInvoiceCreateTotals:
    """T-11: server computes; client totals ignored (BL-2)."""

    def test_server_computes_subtotal_and_total(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        resp = _post_invoice(Client(), headers, _base_body(billing_setup))
        assert resp.status_code == 201, resp.content[:400]
        data = resp.json()
        # 1500.00 x1 + 800.00 x2 = 3100.00
        assert data["subtotal"] == "3100.00"
        assert data["total"] == "3100.00"
        assert data["status"] == "unpaid"

    def test_client_sent_totals_are_ignored(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(billing_setup)
        body["total"] = "999999.99"
        body["subtotal"] = "1.00"
        resp = _post_invoice(Client(), headers, body)
        assert resp.status_code == 201, resp.content[:400]
        data = resp.json()
        assert data["subtotal"] == "3100.00"
        assert data["total"] == "3100.00"


@pytest.mark.django_db
class TestInvoiceIdempotency:
    """T-13: Idempotency-Key contract (BL-4)."""

    def test_missing_idempotency_key_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        resp = _post_invoice(
            Client(), headers, _base_body(billing_setup), idem_key=None
        )
        assert resp.status_code in (400, 422)
        assert resp.json()["error"]["code"] == "idempotency_key_required"

    def test_replay_same_key_same_payload_returns_original(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        client = Client()
        body = _base_body(billing_setup)
        r1 = _post_invoice(client, headers, body, idem_key="replay-001")
        assert r1.status_code == 201
        r2 = _post_invoice(client, headers, body, idem_key="replay-001")
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]
        with tenant_context(tenant_a):
            assert Invoice.objects.count() == 1

    def test_reused_key_different_payload_conflicts(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        client = Client()
        r1 = _post_invoice(
            client, headers, _base_body(billing_setup), idem_key="clash-001"
        )
        assert r1.status_code == 201
        other = _base_body(
            billing_setup,
            items=[{"test_id": str(billing_setup["test_b"].id), "qty": 1}],
        )
        r2 = _post_invoice(client, headers, other, idem_key="clash-001")
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "idempotency_key_reused"


@pytest.mark.django_db
class TestInvoiceDiscountAndStatus:
    """T-20: discount RBAC (BL-3) and zero-total → paid (BL-6)."""

    def test_zero_total_invoice_created_paid(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(
            billing_setup,
            items=[{"test_id": str(billing_setup["test_a"].id), "qty": 1}],
            discount_amount="1500.00",
            discount_reason="Staff welfare full waiver",
        )
        resp = _post_invoice(Client(), headers, body, idem_key="zero-001")
        assert resp.status_code == 201, resp.content[:400]
        data = resp.json()
        assert data["total"] == "0.00"
        assert data["status"] == "paid"

    def test_receptionist_discount_forbidden(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["receptionist"])
        body = _base_body(
            billing_setup,
            discount_amount="100.00",
            discount_reason="Loyalty discount",
        )
        resp = _post_invoice(Client(), headers, body, idem_key="disc-001")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "discount_not_permitted"

    def test_manager_discount_without_reason_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(billing_setup, discount_amount="100.00", discount_reason=None)
        resp = _post_invoice(Client(), headers, body, idem_key="disc-002")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "discount_reason_required"

    def test_manager_discount_with_reason_ok(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(
            billing_setup,
            discount_amount="100.00",
            discount_reason="Corporate tie-up",
        )
        resp = _post_invoice(Client(), headers, body, idem_key="disc-003")
        assert resp.status_code == 201, resp.content[:400]
        data = resp.json()
        assert data["total"] == "3000.00"
        assert data["status"] == "unpaid"


@pytest.mark.django_db
class TestInvoiceSnapshotsAndPricing:
    """BL-1: snapshot description + unit_price; CT-3 test_not_priced."""

    def test_snapshot_wins_over_later_price_change(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(
            billing_setup,
            items=[{"test_id": str(billing_setup["test_a"].id), "qty": 1}],
        )
        resp = _post_invoice(Client(), headers, body, idem_key="snap-001")
        assert resp.status_code == 201
        inv_id = resp.json()["id"]
        with tenant_context(tenant_a):
            # Change the catalog price AFTER invoicing.
            tp = TestPrice.objects.get(test_id=billing_setup["test_a"].id)
            tp.price = Decimal("5000.00")
            tp.save(update_fields=["price"])
            item = InvoiceItem.objects.get(invoice_id=inv_id)
            assert item.unit_price == Decimal("1500.00")
            assert item.description == "CBC Test"

    def test_unpriced_test_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(
            billing_setup,
            items=[{"test_id": str(billing_setup["unpriced"].id), "qty": 1}],
        )
        resp = _post_invoice(Client(), headers, body, idem_key="noprice-001")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "test_not_priced"

    def test_panel_item_snapshots_panel_price(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(
            billing_setup,
            items=[{"panel_id": str(billing_setup["panel"].id), "qty": 1}],
        )
        resp = _post_invoice(Client(), headers, body, idem_key="panel-001")
        assert resp.status_code == 201, resp.content[:400]
        data = resp.json()
        assert data["subtotal"] == "2500.00"
        assert data["items"][0]["description"] == "Basic Panel"


@pytest.mark.django_db
class TestInvoiceValidation:
    """BL-V1 / BL-V2 / strict serializer."""

    def test_money_as_json_number_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(billing_setup, discount_amount=100.00)
        resp = _post_invoice(Client(), headers, body, idem_key="money-001")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "money_must_be_string"

    def test_qty_zero_rejected(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(
            billing_setup,
            items=[{"test_id": str(billing_setup["test_a"].id), "qty": 0}],
        )
        resp = _post_invoice(Client(), headers, body, idem_key="qty-001")
        assert resp.status_code == 422

    def test_duplicate_lines_merged(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(
            billing_setup,
            items=[
                {"test_id": str(billing_setup["test_a"].id), "qty": 1},
                {"test_id": str(billing_setup["test_a"].id), "qty": 2},
            ],
        )
        resp = _post_invoice(Client(), headers, body, idem_key="merge-001")
        assert resp.status_code == 201, resp.content[:400]
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["quantity"] == 3
        assert data["subtotal"] == "4500.00"

    def test_test_and_panel_xor(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        both = _base_body(
            billing_setup,
            items=[
                {
                    "test_id": str(billing_setup["test_a"].id),
                    "panel_id": str(billing_setup["panel"].id),
                    "qty": 1,
                }
            ],
        )
        r1 = _post_invoice(Client(), headers, both, idem_key="xor-001")
        assert r1.status_code == 422
        neither = _base_body(billing_setup, items=[{"qty": 1}])
        r2 = _post_invoice(Client(), headers, neither, idem_key="xor-002")
        assert r2.status_code == 422

    def test_technician_forbidden(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["technician"])
        resp = _post_invoice(
            Client(), headers, _base_body(billing_setup), idem_key="t-001"
        )
        assert resp.status_code == 403

    def test_out_of_scope_patient_404(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        body = _base_body(billing_setup, patient_id=str(uuid.uuid4()))
        resp = _post_invoice(Client(), headers, body, idem_key="nf-001")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestInvoiceAudit:
    """Audit: invoice.created row, same transaction, actor = caller."""

    def test_audit_row_written(
        self, tenant_a: Any, billing_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(billing_setup["manager"])
        resp = _post_invoice(
            Client(), headers, _base_body(billing_setup), idem_key="aud-001"
        )
        assert resp.status_code == 201
        with tenant_context(tenant_a):
            row = AuditLog.objects.get(
                action="invoice.created", entity_id=uuid.UUID(resp.json()["id"])
            )
            assert row.actor_id == billing_setup["manager"].id
            after = row.after_jsonb
            assert isinstance(after, dict)
            assert after["idempotency_key"] == "aud-001"
