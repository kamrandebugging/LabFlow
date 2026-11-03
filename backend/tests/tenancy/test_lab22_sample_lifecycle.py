"""LAB-22 Test Suite: Specimen lifecycle — receive, reject, recollect, cancel
+ samples.notify_rejection (Doc 03 §5.4 SM-5/SM-7..SM-9/SM-11, Doc 06 §6 EV-4,
KAN-138; consolidated from original LAB-24 + LAB-42).

Covers:
- POST /api/v1/samples/{id}/receive (O/M/T): collected -> received only;
  409 invalid_state_transition otherwise; 409 sample_not_here when the
  caller branch does not hold the sample (SM-7); RECEIVED event + audit in
  the same transaction; RBAC (403 for Receptionist).
- POST /api/v1/samples/{id}/reject (O/M/R/T): reason_code required from the
  SM-8 v1 list (-> 422 on unknown); note required ONLY for `other`
  (-> 422 reject_note_required); 409 sample_has_results; 409
  transfer_already_open; 409 invalid_state_transition when already
  rejected/cancelled; -> rejected + code/note stored (A-2) + REJECTED event
  with code + audit, same transaction; enqueues samples.notify_rejection.
- POST /api/v1/samples/{id}/recollect (O/M/R): only on rejected sample
  (-> 409 otherwise); -> 201 new sample, fresh accession, untested
  sample_test rows copied, audit links old -> new accession, events
  sample.recollected + sample.collected; no double billing (invoice
  untouched, SM-9).
- POST /api/v1/samples/{id}/cancel (O/M only): reason required
  (-> 422 cancel_reason_required); only from collected|received (SM-11);
  409 invalid_state_transition otherwise; 409 once any result exists;
  -> cancelled + CANCELLED event + audit, same transaction; 403 for R/T.
- samples.notify_rejection: idempotent per REJECTED event id (second run is
  a no-op); branch notice always; patient notice only under EV-4 (tenant
  permits + patient contact); language from tenant_setting
  report_default_language.
"""

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser, TenantSetting
from apps.billing.models import Invoice
from apps.billing.services import BillingService
from apps.notifications.models import Notification
from apps.results.models import Result
from apps.samples.models import Sample, SampleEvent, SampleTest, SampleTransfer
from tests.factories.branch import BranchFactory
from tests.factories.catalog import TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

SAMPLES_URL = "/api/v1/samples"


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
def lab22_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        other_branch = BranchFactory(code="BR2", name="Second Branch")

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="lc_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="lc_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="lc_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="lc_tech@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )
        other_tech = StaffUserFactory(
            role=Role.TECHNICIAN, branch=other_branch, email="lc_tech2@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=other_tech, branch=other_branch, is_primary=True
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="lc_path@tenant.com"
        )

        patient = PatientFactory(branch=branch)
        test_a = TestFactory(name="CBC", code="CBC001")
        TestPriceFactory(test=test_a, panel=None, price=Decimal("1500.00"))

        return {
            "branch": branch,
            "other_branch": other_branch,
            "owner": owner,
            "manager": manager,
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
            idempotency_key=f"lab22-{uuid.uuid4()}",
            actor=actor,
        )
        return invoice


def _collect_sample(
    tenant_a: Any, setup: dict[str, Any], auth_headers: Any
) -> dict[str, Any]:
    # Collection itself is O/M/R — always collect as the receptionist,
    # regardless of which role the test's action headers belong to.
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


def _sample_row(tenant_a: Any, sample_id: str) -> Sample:
    with tenant_context(tenant_a):
        return Sample.objects.get(pk=sample_id)


class TestSampleReceive:
    def test_receive_happy_path(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """collected -> received; RECEIVED event + audit in same transaction."""
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/receive", headers)
        assert resp.status_code == 200, resp.content[:500]
        assert resp.json()["status"] == "received"

        with tenant_context(tenant_a):
            row = Sample.objects.get(pk=sample["id"])
            assert row.status == Sample.Status.RECEIVED
            assert SampleEvent.objects.filter(
                sample=row, event=SampleEvent.EventType.RECEIVED
            ).exists()
            assert AuditLog.objects.filter(
                entity_type="sample",
                entity_id=row.id,
                action="sample.received",
            ).exists()

    def test_receive_twice_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        assert (
            _post(
                Client(), f"{SAMPLES_URL}/{sample['id']}/receive", headers
            ).status_code
            == 200
        )
        resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/receive", headers)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_receive_wrong_branch_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SM-7: receipt by a branch that does not hold the sample -> 409."""
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        other_headers = auth_headers(lab22_setup["other_tech"])
        resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/receive", other_headers)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "sample_not_here"

    def test_receive_roles(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """O/M/T allowed; Receptionist and Pathologist -> 403."""
        for role_name, allowed in [
            ("owner", True),
            ("manager", True),
            ("technician", True),
            ("receptionist", False),
            ("pathologist", False),
        ]:
            sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
            headers = auth_headers(lab22_setup[role_name])
            resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/receive", headers)
            if allowed:
                assert resp.status_code == 200, (role_name, resp.content[:300])
            else:
                assert resp.status_code == 403, (role_name, resp.content[:300])

    def test_receive_404(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["technician"])
        resp = _post(Client(), f"{SAMPLES_URL}/{uuid.uuid4()}/receive", headers)
        assert resp.status_code == 404


class TestSampleReject:
    def test_reject_happy_path(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """-> rejected; code stored (A-2); REJECTED event + audit; task enqueued."""
        from unittest.mock import patch

        from django.test import TestCase

        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        # The broker isn't available in tests: mock delay, but still verify the
        # enqueue happens via transaction.on_commit.
        with (
            patch("apps.samples.tasks.notify_rejection_task.delay") as mock_delay,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            resp = _post(
                Client(),
                f"{SAMPLES_URL}/{sample['id']}/reject",
                headers,
                {"reason_code": "hemolyzed"},
            )
        assert resp.status_code == 200, resp.content[:500]
        assert resp.json()["status"] == "rejected"
        mock_delay.assert_called_once()
        enqueued_schema, enqueued_event_id = mock_delay.call_args[0]
        assert enqueued_event_id

        with tenant_context(tenant_a):
            row = Sample.objects.get(pk=sample["id"])
            assert row.status == Sample.Status.REJECTED
            assert row.rejection_reason_code == "hemolyzed"
            event = SampleEvent.objects.get(
                sample=row, event=SampleEvent.EventType.REJECTED
            )
            assert str(event.id) == enqueued_event_id
            audit = AuditLog.objects.get(
                entity_type="sample", entity_id=row.id, action="sample.rejected"
            )
            assert audit.after_jsonb is not None
            assert audit.after_jsonb["rejection_reason_code"] == "hemolyzed"

    def test_reject_unknown_code_422(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/reject",
            headers,
            {"reason_code": "melted"},
        )
        assert resp.status_code == 422

    def test_reject_other_requires_note(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SM-8: note mandatory when code is `other`."""
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/reject",
            headers,
            {"reason_code": "other"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "reject_note_required"

        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/reject",
            headers,
            {"reason_code": "other", "note": "Tube cracked in transit"},
        )
        assert resp.status_code == 200
        row = _sample_row(tenant_a, sample["id"])
        assert row.rejection_note == "Tube cracked in transit"

    def test_reject_note_optional_otherwise(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/reject",
            headers,
            {"reason_code": "clotted", "note": "visible clots"},
        )
        assert resp.status_code == 200
        row = _sample_row(tenant_a, sample["id"])
        assert row.rejection_note == "visible clots"

    def test_reject_with_results_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        with tenant_context(tenant_a):
            row = Sample.objects.get(pk=sample["id"])
            st = SampleTest.objects.filter(sample=row).first()
            assert st is not None
            Result.objects.create(
                sample=row,
                test=st.test,
                value="5.0",
                unit="x10^9/L",
                status=Result.Status.ENTERED,
                entered_by=lab22_setup["technician"],
            )
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/reject",
            headers,
            {"reason_code": "hemolyzed"},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "sample_has_results"

    def test_reject_open_transfer_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        with tenant_context(tenant_a):
            row = Sample.objects.get(pk=sample["id"])
            SampleTransfer.objects.create(
                sample=row,
                from_branch=lab22_setup["branch"],
                to_branch=lab22_setup["other_branch"],
                transferred_by=lab22_setup["technician"],
                status=SampleTransfer.Status.OPEN,
            )
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/reject",
            headers,
            {"reason_code": "hemolyzed"},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "transfer_already_open"

    def test_reject_already_rejected_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        body = {"reason_code": "hemolyzed"}
        assert (
            _post(
                Client(), f"{SAMPLES_URL}/{sample['id']}/reject", headers, body
            ).status_code
            == 200
        )
        resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/reject", headers, body)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_reject_roles(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """O/M/R/T allowed; Pathologist -> 403."""
        for role_name, allowed in [
            ("owner", True),
            ("manager", True),
            ("receptionist", True),
            ("technician", True),
            ("pathologist", False),
        ]:
            sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
            headers = auth_headers(lab22_setup[role_name])
            resp = _post(
                Client(),
                f"{SAMPLES_URL}/{sample['id']}/reject",
                headers,
                {"reason_code": "hemolyzed"},
            )
            if allowed:
                assert resp.status_code == 200, (role_name, resp.content[:300])
            else:
                assert resp.status_code == 403, (role_name, resp.content[:300])


class TestSampleRecollect:
    def test_recollect_happy_path(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """201 new sample: fresh accession, untested tests copied, audit link."""
        headers = auth_headers(lab22_setup["receptionist"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        tech_headers = auth_headers(lab22_setup["technician"])
        assert (
            _post(
                Client(),
                f"{SAMPLES_URL}/{sample['id']}/reject",
                tech_headers,
                {"reason_code": "hemolyzed"},
            ).status_code
            == 200
        )

        old_accession = sample["accession_id"]
        resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/recollect", headers)
        assert resp.status_code == 201, resp.content[:500]
        new = resp.json()
        assert new["accession_id"] != old_accession
        assert new["status"] == "collected"

        with tenant_context(tenant_a):
            old_row = Sample.objects.get(pk=sample["id"])
            new_row = Sample.objects.get(pk=new["id"])
            assert old_row.status == Sample.Status.REJECTED  # unchanged
            # untested sample_test rows copied
            old_tests = set(
                SampleTest.objects.filter(sample=old_row).values_list(
                    "test_id", flat=True
                )
            )
            new_tests = set(
                SampleTest.objects.filter(sample=new_row).values_list(
                    "test_id", flat=True
                )
            )
            assert old_tests == new_tests and len(new_tests) > 0
            # new sample has its own COLLECTED event
            assert SampleEvent.objects.filter(
                sample=new_row, event=SampleEvent.EventType.COLLECTED
            ).exists()
            # audit links old -> new accession
            audit = AuditLog.objects.get(
                entity_type="sample",
                entity_id=old_row.id,
                action="sample.recollected",
            )
            assert audit.after_jsonb is not None
            assert audit.after_jsonb["old_accession_id"] == old_accession
            assert audit.after_jsonb["new_accession_id"] == new["accession_id"]
            assert AuditLog.objects.filter(
                entity_type="sample",
                entity_id=new_row.id,
                action="sample.collected",
            ).exists()

    def test_recollect_not_rejected_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["receptionist"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/recollect", headers)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_recollect_no_double_billing(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SM-9: recollect never touches the invoice."""
        headers = auth_headers(lab22_setup["receptionist"])
        inv = _make_invoice(tenant_a, lab22_setup, lab22_setup["receptionist"])
        with tenant_context(tenant_a):
            total_before = Invoice.objects.get(pk=inv.id).total
            invoice_count_before = Invoice.objects.count()
        resp = Client().post(
            SAMPLES_URL,
            data=json.dumps({"invoice_id": str(inv.id)}),
            content_type="application/json",
            headers=headers,
        )
        assert resp.status_code == 201
        sample_id = resp.json()["id"]
        tech_headers = auth_headers(lab22_setup["technician"])
        assert (
            _post(
                Client(),
                f"{SAMPLES_URL}/{sample_id}/reject",
                tech_headers,
                {"reason_code": "hemolyzed"},
            ).status_code
            == 200
        )
        assert (
            _post(Client(), f"{SAMPLES_URL}/{sample_id}/recollect", headers).status_code
            == 201
        )
        with tenant_context(tenant_a):
            assert Invoice.objects.count() == invoice_count_before
            assert Invoice.objects.get(pk=inv.id).total == total_before

    def test_recollect_technician_403(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        tech_headers = auth_headers(lab22_setup["technician"])
        assert (
            _post(
                Client(),
                f"{SAMPLES_URL}/{sample['id']}/reject",
                tech_headers,
                {"reason_code": "hemolyzed"},
            ).status_code
            == 200
        )
        resp = _post(Client(), f"{SAMPLES_URL}/{sample['id']}/recollect", tech_headers)
        assert resp.status_code == 403


class TestSampleCancel:
    def test_cancel_from_collected(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["manager"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/cancel",
            headers,
            {"reason": "Duplicate order"},
        )
        assert resp.status_code == 200, resp.content[:500]
        assert resp.json()["status"] == "cancelled"
        with tenant_context(tenant_a):
            row = Sample.objects.get(pk=sample["id"])
            assert row.status == Sample.Status.CANCELLED
            assert SampleEvent.objects.filter(
                sample=row, event=SampleEvent.EventType.CANCELLED
            ).exists()
            assert AuditLog.objects.filter(
                entity_type="sample", entity_id=row.id, action="sample.cancelled"
            ).exists()

    def test_cancel_from_received(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        tech_headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        assert (
            _post(
                Client(), f"{SAMPLES_URL}/{sample['id']}/receive", tech_headers
            ).status_code
            == 200
        )
        mgr_headers = auth_headers(lab22_setup["manager"])
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/cancel",
            mgr_headers,
            {"reason": "Patient left"},
        )
        assert resp.status_code == 200

    def test_cancel_reason_required(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        headers = auth_headers(lab22_setup["manager"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        for body in [{}, {"reason": ""}, {"reason": "   "}]:
            resp = _post(
                Client(), f"{SAMPLES_URL}/{sample['id']}/cancel", headers, body
            )
            assert resp.status_code == 422, (body, resp.content[:300])
            assert resp.json()["error"]["code"] == "cancel_reason_required"

    def test_cancel_roles(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """O/M only; Receptionist and Technician -> 403."""
        for role_name, allowed in [
            ("owner", True),
            ("manager", True),
            ("receptionist", False),
            ("technician", False),
        ]:
            sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
            headers = auth_headers(lab22_setup[role_name])
            resp = _post(
                Client(),
                f"{SAMPLES_URL}/{sample['id']}/cancel",
                headers,
                {"reason": "test"},
            )
            if allowed:
                assert resp.status_code == 200, (role_name, resp.content[:300])
            else:
                assert resp.status_code == 403, (role_name, resp.content[:300])

    def test_cancel_rejected_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        tech_headers = auth_headers(lab22_setup["technician"])
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        assert (
            _post(
                Client(),
                f"{SAMPLES_URL}/{sample['id']}/reject",
                tech_headers,
                {"reason_code": "hemolyzed"},
            ).status_code
            == 200
        )
        mgr_headers = auth_headers(lab22_setup["manager"])
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/cancel",
            mgr_headers,
            {"reason": "test"},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_cancel_with_results_409(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """SM-11: once any result exists (even entered), no cancellation."""
        sample = _collect_sample(tenant_a, lab22_setup, auth_headers)
        with tenant_context(tenant_a):
            row = Sample.objects.get(pk=sample["id"])
            st = SampleTest.objects.filter(sample=row).first()
            assert st is not None
            Result.objects.create(
                sample=row,
                test=st.test,
                value="5.0",
                unit="x10^9/L",
                status=Result.Status.ENTERED,
                entered_by=lab22_setup["technician"],
            )
        mgr_headers = auth_headers(lab22_setup["manager"])
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/cancel",
            mgr_headers,
            {"reason": "test"},
        )
        assert resp.status_code == 409


class TestNotifyRejectionTask:
    def _reject_and_event(
        self,
        tenant_a: Any,
        setup: dict[str, Any],
        auth_headers: Any,
        headers: dict[str, str],
    ) -> Any:
        # Task side effects are tested by calling the task function directly
        # (no broker in tests); here we only need the REJECTED event row.
        sample = _collect_sample(tenant_a, setup, auth_headers)
        resp = _post(
            Client(),
            f"{SAMPLES_URL}/{sample['id']}/reject",
            headers,
            {"reason_code": "hemolyzed"},
        )
        assert resp.status_code == 200
        with tenant_context(tenant_a):
            return SampleEvent.objects.get(
                sample_id=sample["id"], event=SampleEvent.EventType.REJECTED
            )

    def test_task_idempotent(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """Second run for the same REJECTED event is a no-op."""
        from apps.samples.tasks import notify_rejection_task

        headers = auth_headers(lab22_setup["technician"])
        event = self._reject_and_event(tenant_a, lab22_setup, auth_headers, headers)
        with tenant_context(tenant_a):
            schema = tenant_a.schema_name
        # first run records the branch notice
        notify_rejection_task(str(schema), str(event.id))
        with tenant_context(tenant_a):
            before = Notification.objects.filter(
                idempotency_key__startswith=f"sample_rejection:{event.id}"
            ).count()
        assert before >= 1
        # second and third runs must not duplicate
        notify_rejection_task(str(schema), str(event.id))
        notify_rejection_task(str(schema), str(event.id))
        with tenant_context(tenant_a):
            after = Notification.objects.filter(
                idempotency_key__startswith=f"sample_rejection:{event.id}"
            ).count()
        assert after == before

    def test_patient_notice_ev4(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """EV-4: no patient row by default; with tenant opt-in -> patient row."""
        headers = auth_headers(lab22_setup["technician"])
        event = self._reject_and_event(tenant_a, lab22_setup, auth_headers, headers)
        with tenant_context(tenant_a):
            # default: tenant does not permit -> no patient notice
            assert not Notification.objects.filter(
                idempotency_key=f"sample_rejection:{event.id}:patient"
            ).exists()
            # opt in
            TenantSetting.objects.create(
                key="patient_rejection_notices_enabled", value="true"
            )
        from apps.samples.tasks import notify_rejection_task

        with tenant_context(tenant_a):
            schema = tenant_a.schema_name
        # new rejection so the task runs fresh
        event2 = self._reject_and_event(tenant_a, lab22_setup, auth_headers, headers)
        notify_rejection_task(str(schema), str(event2.id))
        with tenant_context(tenant_a):
            row = Notification.objects.get(
                idempotency_key=f"sample_rejection:{event2.id}:patient"
            )
            assert row.recipient_type == "patient"
            assert row.template_key == "sample_rejected"
            assert row.status == "PENDING"

    def test_rejection_language_from_tenant_setting(
        self, tenant_a: Any, lab22_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """A-16: notice language from tenant_setting report_default_language."""
        from apps.samples.tasks import notify_rejection_task

        with tenant_context(tenant_a):
            TenantSetting.objects.create(key="report_default_language", value="ur")
            schema = tenant_a.schema_name
        headers = auth_headers(lab22_setup["technician"])
        event = self._reject_and_event(tenant_a, lab22_setup, auth_headers, headers)
        result = notify_rejection_task(str(schema), str(event.id))
        assert result["locale"] == "ur"
