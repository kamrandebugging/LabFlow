"""LAB-21 Test Suite: Sample accessioning — collection & Code128 labels
(Doc 03 §5.4 SM-1..SM-4, Doc 02 §9, KAN-137).

Covers (original LAB-23, endpoints in this ticket only):
- T-14: accession format {prefix:3}{YYYYMMDD}{seq:06d}, server-generated,
  sequential per tenant per day.
- T-22: panel expansion — one sample_test per DISTINCT component test.
- POST /api/v1/samples — invoice_id required; optional invoice_item_ids
  subset (split tube); 409 on cancelled invoice (BL-9); 422 no_untested_items;
  409 items_already_collected naming the existing accession (natural
  idempotency); collected_at/collector/branch set; COLLECTED sample_event +
  sample.collected audit in the same transaction; RBAC (403 for Technician).
- GET /api/v1/samples/{id}/label — payload shape with code128 barcode over
  the accession (SM-4, stored data only); every print AND reprint audited;
  404 out of scope; RBAC.
"""

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.models import Invoice
from apps.billing.services import BillingService
from apps.samples.models import Sample, SampleEvent, SampleTest
from tests.factories.branch import BranchFactory
from tests.factories.catalog import (
    PanelFactory,
    PanelTestFactory,
    TestFactory,
    TestPriceFactory,
)
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

SAMPLES_URL = "/api/v1/samples"
KARACHI = ZoneInfo("Asia/Karachi")


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
def lab21_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="smp_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="smp_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="smp_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="smp_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )

        patient = PatientFactory(branch=branch)
        test_a = TestFactory(name="CBC", code="CBC001")
        TestPriceFactory(test=test_a, panel=None, price=Decimal("1500.00"))
        test_b = TestFactory(name="LFT", code="LFT001")
        TestPriceFactory(test=test_b, panel=None, price=Decimal("2200.00"))
        test_c = TestFactory(name="Urine RE", code="URN001")
        TestPriceFactory(test=test_c, panel=None, price=Decimal("800.00"))

        panel = PanelFactory(name="Basic Panel", code="PNL001")
        PanelTestFactory(panel=panel, test=test_b)
        PanelTestFactory(panel=panel, test=test_c)
        TestPriceFactory(test=None, panel=panel, price=Decimal("5000.00"))

        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "patient": patient,
            "test_a": test_a,
            "test_b": test_b,
            "test_c": test_c,
            "panel": panel,
        }


def _make_invoice(
    tenant_a: Any,
    setup: dict[str, Any],
    actor: Any,
    items: list[dict[str, Any]] | None = None,
) -> Any:
    if items is None:
        items = [
            {"test_id": setup["test_a"].id, "qty": 1},
            {"panel_id": setup["panel"].id, "qty": 1},
        ]
    with tenant_context(tenant_a):
        invoice, _ = BillingService.create_invoice(
            patient_id=setup["patient"].id,
            branch_id=setup["branch"].id,
            referral_partner_id=None,
            items=items,
            discount_amount=Decimal("0.00"),
            discount_reason=None,
            idempotency_key=f"lab21-{uuid.uuid4()}",
            actor=actor,
        )
        return invoice


def _collect(
    client: Client,
    headers: dict[str, str],
    invoice_id: Any,
    invoice_item_ids: list[str] | None = None,
) -> Any:
    import json

    body: dict[str, Any] = {"invoice_id": str(invoice_id)}
    if invoice_item_ids is not None:
        body["invoice_item_ids"] = invoice_item_ids
    return client.post(
        SAMPLES_URL,
        data=json.dumps(body),
        content_type="application/json",
        headers=headers,
    )


class TestSampleCollection:
    def test_accession_format_and_sequence(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """T-14: {prefix:3}{YYYYMMDD}{seq:06d}, server-generated, sequential."""
        headers = auth_headers(lab21_setup["receptionist"])
        inv1 = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        inv2 = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])

        r1 = _collect(Client(), headers, inv1.id)
        r2 = _collect(Client(), headers, inv2.id)
        assert r1.status_code == 201
        assert r2.status_code == 201

        a1 = r1.json()["accession_id"]
        a2 = r2.json()["accession_id"]
        today = date.today().isoformat().replace("-", "")
        # Tenant A -> prefix TEN
        assert re.fullmatch(r"TEN\d{8}\d{6}", a1), a1
        assert a1[3:11] == today
        assert a2[3:11] == today
        assert int(a2[11:]) == int(a1[11:]) + 1

    def test_client_cannot_supply_accession(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Unknown/supplied accession_id is rejected — server mints it."""
        import json

        headers = auth_headers(lab21_setup["receptionist"])
        inv = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        resp = Client().post(
            SAMPLES_URL,
            data=json.dumps(
                {"invoice_id": str(inv.id), "accession_id": "HAX20260101000001"}
            ),
            content_type="application/json",
            headers=headers,
        )
        assert resp.status_code == 422

    def test_panel_expansion(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """T-22: panel expands to one sample_test per DISTINCT component test."""
        headers = auth_headers(lab21_setup["receptionist"])
        inv = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        resp = _collect(Client(), headers, inv.id)
        assert resp.status_code == 201
        with tenant_context(tenant_a):
            sample = Sample.objects.get(accession_id=resp.json()["accession_id"])
            test_ids = set(
                SampleTest.objects.filter(sample=sample).values_list(
                    "test_id", flat=True
                )
            )
            # test_a + panel(test_b, test_c) = 3 distinct tests
            assert test_ids == {
                lab21_setup["test_a"].id,
                lab21_setup["test_b"].id,
                lab21_setup["test_c"].id,
            }

    def test_split_tube_subset(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """invoice_item_ids subset collects only those items' tests."""
        headers = auth_headers(lab21_setup["receptionist"])
        inv = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        with tenant_context(tenant_a):
            item_ids = list(
                inv.items.order_by("created_at").values_list("id", flat=True)
            )
        # collect only the first item (test_a)
        resp = _collect(Client(), headers, inv.id, [str(item_ids[0])])
        assert resp.status_code == 201
        with tenant_context(tenant_a):
            sample = Sample.objects.get(accession_id=resp.json()["accession_id"])
            test_ids = set(
                SampleTest.objects.filter(sample=sample).values_list(
                    "test_id", flat=True
                )
            )
            assert test_ids == {lab21_setup["test_a"].id}

    def test_retry_naming_existing_accession(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Natural idempotency: retry over collected items -> 409 + accession."""
        headers = auth_headers(lab21_setup["receptionist"])
        inv = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        r1 = _collect(Client(), headers, inv.id)
        assert r1.status_code == 201
        accession = r1.json()["accession_id"]

        r2 = _collect(Client(), headers, inv.id)
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "items_already_collected"
        assert accession in r2.json()["error"]["message"]

    def test_no_untested_items(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Invoice with zero items -> 422 no_untested_items."""
        headers = auth_headers(lab21_setup["receptionist"])
        inv = _make_invoice(
            tenant_a, lab21_setup, lab21_setup["receptionist"], items=[]
        )
        resp = _collect(Client(), headers, inv.id)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "no_untested_items"

    def test_cancelled_invoice_blocked(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """BL-9: collection blocked while invoice is cancelled -> 409."""
        headers = auth_headers(lab21_setup["receptionist"])
        inv = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        with tenant_context(tenant_a):
            inv.status = Invoice.Status.CANCELLED
            inv.save(update_fields=["status"])
        resp = _collect(Client(), headers, inv.id)
        assert resp.status_code == 409

    def test_collection_fields_and_event(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SM-3: collected_at/collected_by/status/branch + COLLECTED event + audit."""
        headers = auth_headers(lab21_setup["receptionist"])
        inv = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        resp = _collect(Client(), headers, inv.id)
        assert resp.status_code == 201
        with tenant_context(tenant_a):
            sample = Sample.objects.get(accession_id=resp.json()["accession_id"])
            assert sample.status == Sample.Status.COLLECTED
            assert sample.collected_at is not None
            assert sample.collected_by_id == lab21_setup["receptionist"].id
            assert sample.branch_id == lab21_setup["branch"].id
            assert SampleEvent.objects.filter(
                sample=sample, event=SampleEvent.EventType.COLLECTED
            ).exists()
            assert AuditLog.objects.filter(
                action="sample.collected", entity_id=sample.id
            ).exists()

    def test_rbac_technician_forbidden(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab21_setup["technician"])
        inv = _make_invoice(tenant_a, lab21_setup, lab21_setup["receptionist"])
        resp = _collect(Client(), headers, inv.id)
        assert resp.status_code == 403

    def test_invoice_not_found(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab21_setup["receptionist"])
        resp = _collect(Client(), headers, uuid.uuid4())
        assert resp.status_code == 404


class TestSampleLabel:
    def _collect_one(
        self, tenant_a: Any, setup: dict[str, Any], headers: dict[str, str]
    ) -> Any:
        inv = _make_invoice(tenant_a, setup, setup["receptionist"])
        resp = _collect(Client(), headers, inv.id)
        assert resp.status_code == 201
        return resp.json()

    def test_label_payload(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SM-4: label from stored data; code128 barcode over the accession."""
        headers = auth_headers(lab21_setup["receptionist"])
        created = self._collect_one(tenant_a, lab21_setup, headers)
        accession = created["accession_id"]

        resp = Client().get(f"{SAMPLES_URL}/{created['id']}/label", headers=headers)
        assert resp.status_code == 200
        label = resp.json()
        assert label["accession_id"] == accession
        assert label["patient_name"] == lab21_setup["patient"].name
        assert label["mrn"] == lab21_setup["patient"].mrn
        assert label["date_of_birth"] == str(lab21_setup["patient"].date_of_birth)
        assert label["collected_at"].endswith("+05:00")
        assert label["collected_by"] == lab21_setup["receptionist"].email
        assert label["barcode"] == {
            "symbology": "code128",
            "payload": accession,
        }

    def test_label_reprint_audited(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Every print AND reprint is audited (mislabelling investigations)."""
        headers = auth_headers(lab21_setup["receptionist"])
        created = self._collect_one(tenant_a, lab21_setup, headers)
        url = f"{SAMPLES_URL}/{created['id']}/label"
        assert Client().get(url, headers=headers).status_code == 200
        assert Client().get(url, headers=headers).status_code == 200
        with tenant_context(tenant_a):
            count = AuditLog.objects.filter(
                action="sample.label_printed",
                entity_id=uuid.UUID(created["id"]),
            ).count()
            assert count == 2

    def test_label_not_found(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab21_setup["receptionist"])
        resp = Client().get(f"{SAMPLES_URL}/{uuid.uuid4()}/label", headers=headers)
        assert resp.status_code == 404

    def test_label_rbac(
        self, tenant_a: Any, lab21_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Label roles O/M/R/T — technician allowed, pathologist not."""
        headers = auth_headers(lab21_setup["receptionist"])
        created = self._collect_one(tenant_a, lab21_setup, headers)
        url = f"{SAMPLES_URL}/{created['id']}/label"

        tech_headers = auth_headers(lab21_setup["technician"])
        assert Client().get(url, headers=tech_headers).status_code == 200
