"""LAB-23 Test Suite: Inter-branch sample transfer — custody timeline,
receipt, exceptions & lost tracking (Doc 03 §5.4 SM-5/SM-7, Doc 04 §9.2/§9.4,
Doc 03 §6.5/§11, KAN-143; consolidated from original LAB-25 + LAB-26 + LAB-46).

Covers:
- POST /api/v1/samples/{id}/transfer (O/M/R/T): to_branch_id required;
  only from collected|received (-> 409 invalid_state_transition for
  in_process etc.); 409 transfer_already_open; 422 branch_cannot_receive
  for collection-centre / soft-deleted destination; 404 unknown
  destination; 409 sample_not_here when the caller branch does not hold
  the sample; -> 201 transfer (open, dispatched_at=now), sample status
  UNCHANGED while open (SM-7), TRANSFERRED_OUT event + audit
  transfer.created in the same transaction.
- POST /api/v1/transfers/{id}/receive (O/M/R/T): caller scoped to the
  destination branch (-> 404 otherwise); 409 invalid_state_transition
  when not open; -> received + received_at, TRANSFERRED_IN + RECEIVED
  events, sample.branch_id moves to destination, sample status ->
  received (SM-7); audit transfer.received, same transaction.
- POST /api/v1/transfers/{id}/cancel (O/M only): sending-branch scope
  (-> 404); 403 for R/T; 409 when not open; -> cancelled +
  TRANSFER_CANCELLED event; sample stays at sender in prior status
  (transferable again); audit transfer.cancelled.
- POST /api/v1/transfers/{id}/mark-lost (O/M only): note required
  (-> 422 mark_lost_note_required); sending-branch scope (-> 404);
  403 for R/T; 409 when not open; -> lost + TRANSFER_LOST event with
  note; sample status UNCHANGED (SM-7); audit transfer.marked_lost.
- GET /api/v1/samples/{id}/events (O/M/R/T/P): read-only chain-of-custody
  timeline (R-5): event, actor, branch, timestamp, payload (rejection
  code, transfer branches); 404 out of scope; no audit row written.
- GET /api/v1/transfers/exceptions (O/M only): late (open transfers older
  than transfer_late_after_hours, default 24 — report only, no state
  moves), lost (status lost + from/to period filter), route_health (per
  from->to pair counts + month filter); Manager sees only pairs touching
  own branches; 403 for R/T/P.
"""

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser, TenantSetting
from apps.billing.services import BillingService
from apps.samples.models import Sample, SampleEvent, SampleTransfer
from tests.factories.branch import BranchFactory
from tests.factories.catalog import TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

SAMPLES_URL = "/api/v1/samples"
TRANSFERS_URL = "/api/v1/transfers"


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
def lab23_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        other_branch = BranchFactory(code="BR2", name="Second Branch")
        third_branch = BranchFactory(code="BR3", name="Third Branch")
        coll_branch = BranchFactory(
            code="CC1", name="Collection Centre", is_collection_centre=True
        )

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="t23_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="t23_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        manager2 = StaffUserFactory(
            role=Role.MANAGER, branch=other_branch, email="t23_manager2@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=manager2, branch=other_branch, is_primary=True
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="t23_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="t23_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )
        other_tech = StaffUserFactory(
            role=Role.TECHNICIAN, branch=other_branch, email="t23_tech2@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=other_tech, branch=other_branch, is_primary=True
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="t23_path@tenant.com"
        )

        patient = PatientFactory(branch=branch)
        test_a = TestFactory(name="CBC", code="CBC001")
        TestPriceFactory(test=test_a, panel=None, price=Decimal("1500.00"))

        return {
            "branch": branch,
            "other_branch": other_branch,
            "third_branch": third_branch,
            "coll_branch": coll_branch,
            "owner": owner,
            "manager": manager,
            "manager2": manager2,
            "receptionist": receptionist,
            "technician": technician,
            "other_tech": other_tech,
            "pathologist": pathologist,
            "patient": patient,
            "test_a": test_a,
        }


def _make_invoice(tenant_a: Any, setup: dict[str, Any], actor: Any) -> Any:
    with tenant_context(tenant_a):
        invoice, _ = BillingService.create_invoice(
            patient_id=setup["patient"].id,
            branch_id=setup["branch"].id,
            referral_partner_id=None,
            items=[{"test_id": setup["test_a"].id, "qty": 1}],
            discount_amount=Decimal("0.00"),
            discount_reason=None,
            idempotency_key=f"lab23-{uuid.uuid4()}",
            actor=actor,
        )
        return invoice


def _collect_sample(
    tenant_a: Any, setup: dict[str, Any], auth_headers: Any
) -> dict[str, Any]:
    headers = auth_headers(setup["receptionist"])
    inv = _make_invoice(tenant_a, setup, setup["receptionist"])
    resp = Client().post(
        SAMPLES_URL,
        data=json.dumps({"invoice_id": str(inv.id)}),
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 201, resp.content[:500]
    return resp.json()


def _post(client: Client, url: str, headers: dict[str, str], body: Any = None) -> Any:
    kwargs: dict[str, Any] = {
        "content_type": "application/json",
        "headers": headers,
    }
    if body is not None:
        kwargs["data"] = json.dumps(body)
    return client.post(url, **kwargs)


def _get(client: Client, url: str, headers: dict[str, str]) -> Any:
    return client.get(url, headers=headers)


def _transfer(
    tenant_a: Any,
    setup: dict[str, Any],
    auth_headers: Any,
    sample_id: str,
    to_branch_id: str,
    actor_key: str = "manager",
) -> Any:
    headers = auth_headers(setup[actor_key])
    return _post(
        Client(),
        f"{SAMPLES_URL}/{sample_id}/transfer",
        headers,
        {"to_branch_id": to_branch_id},
    )


def _sample_row(tenant_a: Any, sample_id: str) -> Sample:
    with tenant_context(tenant_a):
        return Sample.objects.get(pk=sample_id)


def _transfer_row(tenant_a: Any, transfer_id: str) -> SampleTransfer:
    with tenant_context(tenant_a):
        return SampleTransfer.objects.get(pk=transfer_id)


def _events(tenant_a: Any, sample_id: str) -> list[str]:
    with tenant_context(tenant_a):
        return list(
            SampleEvent.objects.filter(sample_id=sample_id)
            .order_by("created_at")
            .values_list("event", flat=True)
        )


# ----------------------------------------------------------------------
# A. POST /api/v1/samples/{id}/transfer
# ----------------------------------------------------------------------


class TestTransferCreate:
    def test_t24_transfer_happy_path(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """T-24: transfer creates an open transfer; sample status unchanged."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)

        with tenant_context(tenant_a):
            audit_before = AuditLog.objects.count()
        resp = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        )
        assert resp.status_code == 201, resp.content[:500]
        body = resp.json()
        assert body["status"] == "open"
        assert body["from_branch"]["code"] == "MN1"
        assert body["to_branch"]["code"] == "BR2"
        assert body["dispatched_at"] is not None
        assert body["received_at"] is None

        # SM-7: sample status does NOT change while the transfer is open.
        row = _sample_row(tenant_a, sample["id"])
        assert row.status == Sample.Status.COLLECTED
        assert str(row.branch_id) == str(setup["branch"].id)

        assert _events(tenant_a, sample["id"]) == ["COLLECTED", "TRANSFERRED_OUT"]
        with tenant_context(tenant_a):
            assert AuditLog.objects.filter(action="transfer.created").count() == 1
            assert AuditLog.objects.count() == audit_before + 1

    def test_transfer_409_from_in_process(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        with tenant_context(tenant_a):
            s = Sample.objects.get(pk=sample["id"])
            s.status = Sample.Status.IN_PROCESS
            s.save(update_fields=["status"])
        resp = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_transfer_409_already_open(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        first = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        )
        assert first.status_code == 201
        second = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["third_branch"].id)
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "transfer_already_open"

    def test_transfer_422_branch_cannot_receive(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """Collection centres cannot receive transfers for processing."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        resp = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["coll_branch"].id)
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "branch_cannot_receive"

    def test_transfer_404_unknown_destination(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        resp = _transfer(tenant_a, setup, auth_headers, sample["id"], str(uuid.uuid4()))
        assert resp.status_code == 404

    def test_transfer_409_sample_not_here(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """A caller at another branch cannot dispatch this sample."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        resp = _transfer(
            tenant_a,
            setup,
            auth_headers,
            sample["id"],
            str(setup["third_branch"].id),
            actor_key="other_tech",
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "sample_not_here"

    def test_transfer_404_unknown_sample(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        headers = auth_headers(setup["manager"])
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{uuid.uuid4()}/transfer",
            headers,
            {"to_branch_id": str(setup["other_branch"].id)},
        )
        assert resp.status_code == 404

    def test_transfer_403_pathologist(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        headers = auth_headers(setup["pathologist"])
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/transfer",
            headers,
            {"to_branch_id": str(setup["other_branch"].id)},
        )
        assert resp.status_code == 403


# ----------------------------------------------------------------------
# B. POST /api/v1/transfers/{id}/receive
# ----------------------------------------------------------------------


class TestTransferReceive:
    def test_receive_happy_path(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """Receive moves the sample: branch -> destination, status -> received."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()

        headers = auth_headers(setup["other_tech"])
        resp = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/receive", headers)
        assert resp.status_code == 200, resp.content[:500]
        body = resp.json()
        assert body["status"] == "received"
        assert body["received_at"] is not None

        trow = _transfer_row(tenant_a, tr["id"])
        assert trow.status == SampleTransfer.Status.RECEIVED
        assert str(trow.received_by_id) == str(setup["other_tech"].id)

        srow = _sample_row(tenant_a, sample["id"])
        assert str(srow.branch_id) == str(setup["other_branch"].id)
        assert srow.status == Sample.Status.RECEIVED

        assert _events(tenant_a, sample["id"]) == [
            "COLLECTED",
            "TRANSFERRED_OUT",
            "TRANSFERRED_IN",
            "RECEIVED",
        ]
        with tenant_context(tenant_a):
            assert AuditLog.objects.filter(action="transfer.received").count() == 1

    def test_receive_404_wrong_branch_scope(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """Only the destination branch may receive."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["technician"])  # sender branch
        resp = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/receive", headers)
        assert resp.status_code == 404

    def test_receive_409_when_not_open(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["other_tech"])
        first = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/receive", headers)
        assert first.status_code == 200
        second = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/receive", headers)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "invalid_state_transition"

    def test_receive_404_unknown_transfer(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        headers = auth_headers(setup["other_tech"])
        resp = _post(Client(), f"{TRANSFERS_URL}/{uuid.uuid4()}/receive", headers)
        assert resp.status_code == 404


# ----------------------------------------------------------------------
# C. POST /api/v1/transfers/{id}/cancel  (T-50)
# ----------------------------------------------------------------------


class TestTransferCancel:
    def test_t50_cancel_happy_path(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """T-50: sender cancels; sample stays put and is transferable again."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()

        headers = auth_headers(setup["manager"])
        resp = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/cancel", headers)
        assert resp.status_code == 200, resp.content[:500]
        assert resp.json()["status"] == "cancelled"

        trow = _transfer_row(tenant_a, tr["id"])
        assert trow.status == SampleTransfer.Status.CANCELLED
        srow = _sample_row(tenant_a, sample["id"])
        assert srow.status == Sample.Status.COLLECTED
        assert str(srow.branch_id) == str(setup["branch"].id)
        assert "TRANSFER_CANCELLED" in _events(tenant_a, sample["id"])

        # Transferable again after cancel.
        again = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["third_branch"].id)
        )
        assert again.status_code == 201

    def test_cancel_403_receptionist(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["receptionist"])
        resp = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/cancel", headers)
        assert resp.status_code == 403

    def test_cancel_404_not_sending_branch(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """The receiver can never cancel — only the sender."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["manager2"])  # destination branch manager
        resp = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/cancel", headers)
        assert resp.status_code == 404

    def test_cancel_409_when_not_open(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["manager"])
        first = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/cancel", headers)
        assert first.status_code == 200
        second = _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/cancel", headers)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "invalid_state_transition"


# ----------------------------------------------------------------------
# D. POST /api/v1/transfers/{id}/mark-lost  (T-51)
# ----------------------------------------------------------------------


class TestTransferMarkLost:
    def test_t51_mark_lost_happy_path(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """T-51: lost never auto-closes the sample (SM-7)."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()

        headers = auth_headers(setup["manager"])
        resp = _post(
            Client(),
            f"{TRANSFERS_URL}/{tr['id']}/mark-lost",
            headers,
            {"note": "Courier van broke down on Ring Road"},
        )
        assert resp.status_code == 200, resp.content[:500]
        assert resp.json()["status"] == "lost"

        trow = _transfer_row(tenant_a, tr["id"])
        assert trow.status == SampleTransfer.Status.LOST
        # Sample status UNCHANGED — resolved later via reject + recollect.
        srow = _sample_row(tenant_a, sample["id"])
        assert srow.status == Sample.Status.COLLECTED
        assert "TRANSFER_LOST" in _events(tenant_a, sample["id"])
        with tenant_context(tenant_a):
            assert AuditLog.objects.filter(action="transfer.marked_lost").count() == 1

    def test_mark_lost_422_note_required(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["manager"])
        for body in ({"note": ""}, {"note": "   "}, {}):
            resp = _post(
                Client(), f"{TRANSFERS_URL}/{tr['id']}/mark-lost", headers, body
            )
            assert resp.status_code == 422, resp.content[:300]
            assert resp.json()["error"]["code"] == "mark_lost_note_required"

    def test_mark_lost_403_receptionist(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["receptionist"])
        resp = _post(
            Client(), f"{TRANSFERS_URL}/{tr['id']}/mark-lost", headers, {"note": "x"}
        )
        assert resp.status_code == 403

    def test_mark_lost_409_when_not_open(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["manager"])
        _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/cancel", headers)
        resp = _post(
            Client(), f"{TRANSFERS_URL}/{tr['id']}/mark-lost", headers, {"note": "x"}
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"


# ----------------------------------------------------------------------
# E. GET /api/v1/samples/{id}/events
# ----------------------------------------------------------------------


class TestSampleEventsTimeline:
    def test_events_timeline_shape(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """Chain-of-custody view: event, actor, branch, timestamp, payload."""
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["other_tech"])
        _post(Client(), f"{TRANSFERS_URL}/{tr['id']}/receive", headers)

        headers = auth_headers(setup["pathologist"])
        resp = _get(Client(), f"{SAMPLES_URL}/{sample['id']}/events", headers)
        assert resp.status_code == 200, resp.content[:500]
        events = resp.json()["events"]
        assert [e["event"] for e in events] == [
            "COLLECTED",
            "TRANSFERRED_OUT",
            "TRANSFERRED_IN",
            "RECEIVED",
        ]
        for e in events:
            assert "actor" in e and "branch" in e and "timestamp" in e
            assert "payload" in e and isinstance(e["payload"], dict)
        out_ev = next(e for e in events if e["event"] == "TRANSFERRED_OUT")
        assert out_ev["payload"]["from_branch"]["code"] == "MN1"
        assert out_ev["payload"]["to_branch"]["code"] == "BR2"
        assert out_ev["actor"] == "t23_manager@tenant.com"
        in_ev = next(e for e in events if e["event"] == "TRANSFERRED_IN")
        assert in_ev["branch"]["code"] == "BR2"

    def test_events_404_out_of_scope(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        headers = auth_headers(setup["pathologist"])
        resp = _get(Client(), f"{SAMPLES_URL}/{uuid.uuid4()}/events", headers)
        assert resp.status_code == 404

    def test_events_read_only_no_audit(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        with tenant_context(tenant_a):
            before = AuditLog.objects.count()
        headers = auth_headers(setup["pathologist"])
        resp = _get(Client(), f"{SAMPLES_URL}/{sample['id']}/events", headers)
        assert resp.status_code == 200
        with tenant_context(tenant_a):
            assert AuditLog.objects.count() == before


# ----------------------------------------------------------------------
# F. GET /api/v1/transfers/exceptions
# ----------------------------------------------------------------------


class TestTransferExceptions:
    def _make_late_transfer(
        self, tenant_a: Any, setup: dict[str, Any], auth_headers: Any, hours: int
    ) -> str:
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        with tenant_context(tenant_a):
            t = SampleTransfer.objects.get(pk=tr["id"])
            t.dispatched_at = timezone.now() - timedelta(hours=hours)
            t.save(update_fields=["dispatched_at"])
        return tr["id"]

    def test_late_report_default_threshold(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """Open transfers older than transfer_late_after_hours (default 24)."""
        setup = lab23_setup
        late_id = self._make_late_transfer(tenant_a, setup, auth_headers, hours=30)
        fresh = _collect_sample(tenant_a, setup, auth_headers)
        _transfer(
            tenant_a, setup, auth_headers, fresh["id"], str(setup["third_branch"].id)
        )

        headers = auth_headers(setup["owner"])
        resp = _get(Client(), f"{TRANSFERS_URL}/exceptions?report=late", headers)
        assert resp.status_code == 200, resp.content[:500]
        late = resp.json()["late"]
        ids = [t["transfer_id"] for t in late]
        assert late_id in ids
        row = next(t for t in late if t["transfer_id"] == late_id)
        assert row["hours_in_transit"] >= 30
        # Report only: the transfer is still open, sample untouched.
        trow = _transfer_row(tenant_a, late_id)
        assert trow.status == SampleTransfer.Status.OPEN

    def test_late_report_custom_threshold(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        self._make_late_transfer(tenant_a, setup, auth_headers, hours=30)
        with tenant_context(tenant_a):
            TenantSetting.objects.create(key="transfer_late_after_hours", value="48")
        headers = auth_headers(setup["owner"])
        resp = _get(Client(), f"{TRANSFERS_URL}/exceptions?report=late", headers)
        assert resp.status_code == 200
        assert [t["transfer_id"] for t in resp.json()["late"]] == []

    def test_lost_report_with_period_filter(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        sample = _collect_sample(tenant_a, setup, auth_headers)
        tr = _transfer(
            tenant_a, setup, auth_headers, sample["id"], str(setup["other_branch"].id)
        ).json()
        headers = auth_headers(setup["manager"])
        _post(
            Client(), f"{TRANSFERS_URL}/{tr['id']}/mark-lost", headers, {"note": "lost"}
        )

        today = timezone.now().date().isoformat()
        resp = _get(
            Client(),
            f"{TRANSFERS_URL}/exceptions?report=lost&from={today}&to={today}",
            headers,
        )
        assert resp.status_code == 200, resp.content[:500]
        lost = resp.json()["lost"]
        assert [t["transfer_id"] for t in lost] == [tr["id"]]
        assert lost[0]["note"] == "lost"

        tomorrow = (timezone.now().date() + timedelta(days=1)).isoformat()
        resp = _get(
            Client(),
            f"{TRANSFERS_URL}/exceptions?report=lost&from={tomorrow}&to={tomorrow}",
            headers,
        )
        assert resp.json()["lost"] == []

    def test_route_health_counts_and_month_filter(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        # MN1 -> BR2 open
        s1 = _collect_sample(tenant_a, setup, auth_headers)
        _transfer(
            tenant_a, setup, auth_headers, s1["id"], str(setup["other_branch"].id)
        )
        # MN1 -> BR2 received
        s2 = _collect_sample(tenant_a, setup, auth_headers)
        tr2 = _transfer(
            tenant_a, setup, auth_headers, s2["id"], str(setup["other_branch"].id)
        ).json()
        _post(
            Client(),
            f"{TRANSFERS_URL}/{tr2['id']}/receive",
            auth_headers(setup["other_tech"]),
        )
        # MN1 -> BR2 lost
        s3 = _collect_sample(tenant_a, setup, auth_headers)
        tr3 = _transfer(
            tenant_a, setup, auth_headers, s3["id"], str(setup["other_branch"].id)
        ).json()
        _post(
            Client(),
            f"{TRANSFERS_URL}/{tr3['id']}/mark-lost",
            auth_headers(setup["manager"]),
            {"note": "lost"},
        )

        month = timezone.now().strftime("%Y-%m")
        headers = auth_headers(setup["owner"])
        resp = _get(
            Client(),
            f"{TRANSFERS_URL}/exceptions?report=route_health&month={month}",
            headers,
        )
        assert resp.status_code == 200, resp.content[:500]
        rows = resp.json()["route_health"]
        pair = next(
            r
            for r in rows
            if r["from_branch"]["code"] == "MN1" and r["to_branch"]["code"] == "BR2"
        )
        assert pair["open"] == 1
        assert pair["received"] == 1
        assert pair["lost"] == 1
        assert pair["late"] >= 0

    def test_manager_sees_only_own_branch_pairs(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        """Manager at MN1 must not see BR2 -> BR3 pairs."""
        setup = lab23_setup
        # BR2 -> BR3 transfer by manager2 (destination BR3).
        s = _collect_sample(tenant_a, setup, auth_headers)
        with tenant_context(tenant_a):
            sample = Sample.objects.get(pk=s["id"])
            sample.branch = setup["other_branch"]
            sample.save(update_fields=["branch"])
        headers2 = auth_headers(setup["manager2"])
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{s['id']}/transfer",
            headers2,
            {"to_branch_id": str(setup["third_branch"].id)},
        )
        assert resp.status_code == 201, resp.content[:500]

        headers = auth_headers(setup["manager"])  # MN1 manager
        resp = _get(Client(), f"{TRANSFERS_URL}/exceptions", headers)
        assert resp.status_code == 200
        body = resp.json()
        for section in ("late", "lost", "route_health"):
            for row in body[section]:
                if section == "route_health":
                    codes = {row["from_branch"]["code"], row["to_branch"]["code"]}
                else:
                    codes = {row["from_branch"]["code"], row["to_branch"]["code"]}
                assert "MN1" in codes, f"manager saw foreign pair: {codes}"

        # Owner sees everything.
        oresp = _get(
            Client(), f"{TRANSFERS_URL}/exceptions", auth_headers(setup["owner"])
        )
        assert oresp.status_code == 200
        pairs = {
            (r["from_branch"]["code"], r["to_branch"]["code"])
            for r in oresp.json()["route_health"]
        }
        assert ("BR2", "BR3") in pairs

    def test_exceptions_403_for_receptionist(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        headers = auth_headers(setup["receptionist"])
        resp = _get(Client(), f"{TRANSFERS_URL}/exceptions", headers)
        assert resp.status_code == 403

    def test_exceptions_403_for_pathologist(
        self, tenant_a: Any, lab23_setup: Any, auth_headers: Any
    ) -> None:
        setup = lab23_setup
        headers = auth_headers(setup["pathologist"])
        resp = _get(Client(), f"{TRANSFERS_URL}/exceptions", headers)
        assert resp.status_code == 403
