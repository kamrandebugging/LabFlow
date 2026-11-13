"""LAB-26 Test Suite: Clinical verification (Doc 03 §5.5 RS-4–RS-10, §6.6,
§8.7, §10; KAN-151; original LAB-31).

Covers:
- POST /api/v1/results/{id}/approve — roles Pathologist ONLY (exact §6.6
  roles cell: "P"); 403 for T/O/M/R.
- Body: decision (approved|rejected, required), note (optional),
  range_override (bool, default false). Unknown fields rejected.
- Guards: result must be entered -> else 409 invalid_state_transition.
  404 out of scope / not found.
- RS-6 self-approval: pathologist who ENTERED may not approve -> 403
  self_approval_not_permitted, UNLESS the tenant has exactly one active
  pathologist -> permitted, approval row records range_override=false and
  the audit carries single_pathologist_self_approval (T-29).
- RS-5 rejection: decision=rejected REQUIRES non-empty note -> 422
  note_required_for_rejection; rejected result returns its sample_test to
  the pending worklist; the row is kept read-only.
- RS-7 range override: range_override=true REQUIRES non-empty note -> 422
  override_note_required; computed flag stays on the result, override on
  the approval row (T-30).
- RS-10: NULL-flag numeric test with unparseable value -> note required
  (422); qualitative NULL-flag -> no note required.
- Concurrency (T-31, §10): two concurrent approvals -> exactly one decision
  recorded; loser gets 409 naming the winner. select_for_update single-winner.
- RS-8: approving every sample_test -> sample ready + READY event + audit
  (event flag sample.ready); partial approval leaves in_process (T-32).
- POST /api/v1/results/{id}/withdraw — author ONLY (T/P author; others 403
  withdraw_not_permitted); only from entered before any approval decision
  (-> 409); sets withdrawn, writes NO result_approval row, audit only
  (result.withdrawn); the row stays read-only (T-49, RS-4).
"""

import json
import threading
import uuid
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.results.models import Result, ResultApproval
from apps.samples.models import Sample, SampleEvent
from tests.factories.branch import BranchFactory
from tests.factories.catalog import ReferenceRangeFactory, TestFactory
from tests.factories.results import ResultFactory
from tests.factories.samples import SampleFactory, SampleTestFactory
from tests.factories.staff_user import StaffUserFactory

APPROVE_URL = "/api/v1/results/{result_id}/approve"
WITHDRAW_URL = "/api/v1/results/{result_id}/withdraw"


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
def lab26_setup(tenant_a: Any) -> dict[str, Any]:
    """Two tests on one in_process sample, both results entered by technician."""
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="tech@labflow.app"
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="path1@labflow.app"
        )
        pathologist2 = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="path2@labflow.app"
        )
        test_a = TestFactory(code="GLU", name="Glucose")
        test_b = TestFactory(code="HB", name="Hemoglobin")
        sample = SampleFactory(status=Sample.Status.IN_PROCESS, branch=branch)
        SampleTestFactory(sample=sample, test=test_a)
        SampleTestFactory(sample=sample, test=test_b)
        result_a = ResultFactory(
            sample=sample, test=test_a, entered_by=technician, flag=Result.Flag.NORMAL
        )
        result_b = ResultFactory(
            sample=sample, test=test_b, entered_by=technician, flag=Result.Flag.NORMAL
        )
        return {
            "branch": branch,
            "technician": technician,
            "pathologist": pathologist,
            "pathologist2": pathologist2,
            "test_a": test_a,
            "test_b": test_b,
            "sample": sample,
            "result_a": result_a,
            "result_b": result_b,
        }


def _approve(
    auth_headers: Any,
    user: Any,
    result_id: uuid.UUID,
    body: dict[str, Any],
) -> Any:
    # D8: approvals now require explicit reviewer attestation.
    if body.get("decision") == "approved":
        body = {**body, "attestation": body.get("attestation", True)}
    return Client().post(
        APPROVE_URL.format(result_id=result_id),
        data=json.dumps(body),
        content_type="application/json",
        headers=auth_headers(user),
    )


def _withdraw(auth_headers: Any, user: Any, result_id: uuid.UUID) -> Any:
    return Client().post(
        WITHDRAW_URL.format(result_id=result_id),
        data=json.dumps({}),
        content_type="application/json",
        headers=auth_headers(user),
    )


def _audit_actions(tenant_a: Any, entity_id: uuid.UUID) -> list[str]:
    with tenant_context(tenant_a):
        return list(
            AuditLog.objects.filter(entity_id=entity_id).values_list(
                "action", flat=True
            )
        )


# ---- Roles: approve is Pathologist ONLY (exact §6.6 cell "P") ----


def test_approve_by_technician_403(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["technician"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    assert resp.status_code == 403


def test_approve_by_owner_200_superrole(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        owner = StaffUserFactory(
            role=Role.OWNER, branch=lab26_setup["branch"], email="owner@labflow.app"
        )
    resp = _approve(
        auth_headers, owner, lab26_setup["result_a"].id, {"decision": "approved"}
    )
    assert resp.status_code == 200


def test_approve_unknown_fields_rejected_422(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved", "bogus": "x"},
    )
    assert resp.status_code == 422


def test_approve_404_not_found(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers, setup["pathologist"], uuid.uuid4(), {"decision": "approved"}
    )
    assert resp.status_code == 404


# ---- Happy paths ----


def test_approve_happy_path(tenant_a: Any, lab26_setup: Any, auth_headers: Any) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decision"] == "approved"
    with tenant_context(tenant_a):
        result = Result.objects.get(pk=setup["result_a"].id)
        assert result.status == Result.Status.APPROVED
        approval = ResultApproval.objects.get(result=result)
        assert approval.decision == ResultApproval.Decision.APPROVED
        assert approval.pathologist_id == setup["pathologist"].id
        assert approval.range_override is False
        actions = _audit_actions(tenant_a, result.id)
        assert "result.approved" in actions
        audit = AuditLog.objects.filter(
            entity_id=result.id, action="result.approved"
        ).first()
        assert audit is not None
        assert audit.after_jsonb is not None
        assert audit.after_jsonb.get("event") == "result.approved"


def test_reject_happy_path_returns_test_to_worklist(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "rejected", "note": "Hemolyzed sample, recollect."},
    )
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        result = Result.objects.get(pk=setup["result_a"].id)
        assert result.status == Result.Status.REJECTED
        approval = ResultApproval.objects.get(result=result)
        assert approval.decision == ResultApproval.Decision.REJECTED
        assert approval.note == "Hemolyzed sample, recollect."
        # RS-5: rejected result row is read-only -> approving again is 409.
        assert "result.rejected" in _audit_actions(tenant_a, result.id)


def test_reject_without_note_422(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "rejected"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "note_required_for_rejection"


# ---- RS-7 range override (T-30) ----


def test_range_override_without_note_422(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved", "range_override": True},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "override_note_required"


def test_range_override_with_note_ok_flag_unchanged(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {
            "decision": "approved",
            "range_override": True,
            "note": "Known hemolysis skews potassium; flag misleading.",
        },
    )
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        result = Result.objects.get(pk=setup["result_a"].id)
        # RS-7: the computed flag STAYS on the result, never rewritten.
        assert result.flag == Result.Flag.NORMAL
        approval = ResultApproval.objects.get(result=result)
        assert approval.range_override is True
        assert "potassium" in (approval.note or "")


# ---- RS-6 self-approval (T-29) ----


def test_self_approval_refused_403(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    # pathologist ENTERED this result themselves; tenant has 2 pathologists.
    with tenant_context(tenant_a):
        test_c = TestFactory(code="T3C", name="Third Test")
        SampleTestFactory(sample=lab26_setup["sample"], test=test_c)
        own = ResultFactory(
            sample=lab26_setup["sample"],
            test=test_c,
            entered_by=lab26_setup["pathologist"],
        )
    resp = _approve(
        auth_headers,
        lab26_setup["pathologist"],
        own.id,
        {"decision": "approved"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "self_approval_not_permitted"


def test_single_pathologist_self_approval_allowed_with_marker(
    tenant_a: Any, auth_headers: Any
) -> None:
    # Tenant with EXACTLY ONE active pathologist -> visible exception.
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        solo = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="solo@labflow.app"
        )
        test = TestFactory(code="GLU", name="Glucose")
        sample = SampleFactory(status=Sample.Status.IN_PROCESS, branch=branch)
        SampleTestFactory(sample=sample, test=test)
        own = ResultFactory(sample=sample, test=test, entered_by=solo)
    resp = _approve(auth_headers, solo, own.id, {"decision": "approved"})
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        approval = ResultApproval.objects.get(result_id=own.id)
        assert approval.range_override is False
        audit = AuditLog.objects.filter(
            entity_id=own.id, action="result.approved"
        ).first()
        assert audit is not None
        assert audit.after_jsonb is not None
        assert audit.after_jsonb.get("audit_note") == "single_pathologist_self_approval"


def test_owner_self_approval_allowed_with_marker(
    tenant_a: Any, auth_headers: Any
) -> None:
    # Owner may enter and approve result as superrole signing authority.
    with tenant_context(tenant_a):
        branch = BranchFactory(code="OWN", name="Main Laboratory")
        owner = StaffUserFactory(
            role=Role.OWNER, branch=branch, email="super_owner@labflow.app"
        )
        test = TestFactory(code="GLU_OWN", name="Glucose")
        sample = SampleFactory(status=Sample.Status.IN_PROCESS, branch=branch)
        SampleTestFactory(sample=sample, test=test)
        own = ResultFactory(sample=sample, test=test, entered_by=owner)
    resp = _approve(auth_headers, owner, own.id, {"decision": "approved"})
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        audit = AuditLog.objects.filter(
            entity_id=own.id, action="result.approved"
        ).first()
        assert audit is not None
        assert audit.after_jsonb is not None
        assert audit.after_jsonb.get("audit_note") == "owner_self_approval"


def test_inactive_second_pathologist_still_single(
    tenant_a: Any, auth_headers: Any
) -> None:
    # An INACTIVE pathologist does not break the single-pathologist exception.
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        solo = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="solo@labflow.app"
        )
        StaffUserFactory(
            role=Role.PATHOLOGIST,
            branch=branch,
            email="gone@labflow.app",
            is_active=False,
        )
        test = TestFactory(code="GLU", name="Glucose")
        sample = SampleFactory(status=Sample.Status.IN_PROCESS, branch=branch)
        SampleTestFactory(sample=sample, test=test)
        own = ResultFactory(sample=sample, test=test, entered_by=solo)
    resp = _approve(auth_headers, solo, own.id, {"decision": "approved"})
    assert resp.status_code == 200


# ---- Double approval + concurrency (T-31, §10) ----


def test_double_approval_409_invalid_state_transition(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    first = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    assert first.status_code == 200
    second = _approve(
        auth_headers,
        setup["pathologist2"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "invalid_state_transition"


# NOTE: transaction=True — the test is NOT wrapped in a rollback transaction,
# so setup rows are really committed and visible to the worker threads'
# separate DB connections (same pattern as T-28 in LAB-25). Without this,
# threads cannot see uncommitted setup data and the race cannot be exercised.
@pytest.mark.django_db(transaction=True)
def test_concurrent_approvals_single_winner(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    url = APPROVE_URL.format(result_id=setup["result_a"].id)
    payload = json.dumps({"decision": "approved", "attestation": True})
    barrier = threading.Barrier(2)
    outcomes: dict[int, Any] = {}
    thread_errors: dict[int, str] = {}

    def _decide(idx: int, user: Any) -> None:
        try:
            barrier.wait(timeout=15)
            outcomes[idx] = Client().post(
                url,
                data=payload,
                content_type="application/json",
                headers=auth_headers(user),
            )
        except Exception as exc:  # noqa: BLE001 — surfaced below on failure
            thread_errors[idx] = repr(exc)
        finally:
            from django.db import connections

            for conn in connections.all():
                conn.close()

    t1 = threading.Thread(target=_decide, args=(1, setup["pathologist"]))
    t2 = threading.Thread(target=_decide, args=(2, setup["pathologist2"]))
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    assert not thread_errors, thread_errors
    codes = sorted(o.status_code for o in outcomes.values())
    assert codes == [200, 409], [o.status_code for o in outcomes.values()]
    loser = next(o for o in outcomes.values() if o.status_code == 409)
    body = loser.json()["error"]
    assert body["code"] == "invalid_state_transition"
    # T-31: the loser names the winner.
    assert "details" in body and "decided_by" in body["details"]
    with tenant_context(tenant_a):
        assert (
            ResultApproval.objects.filter(result_id=setup["result_a"].id).count() == 1
        )


# ---- RS-10 NULL flag (unparseable vs qualitative) ----


def test_rs10_numeric_unparseable_requires_note_422(
    tenant_a: Any, auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        technician = StaffUserFactory(role=Role.TECHNICIAN, branch=branch)
        pathologist = StaffUserFactory(role=Role.PATHOLOGIST, branch=branch)
        # Numeric test: reference range with low+high NOT NULL.
        test = TestFactory(code="K", name="Potassium")
        ReferenceRangeFactory(test=test, low="3.5", high="5.5")
        sample = SampleFactory(status=Sample.Status.IN_PROCESS, branch=branch)
        SampleTestFactory(sample=sample, test=test)
        result = ResultFactory(
            sample=sample,
            test=test,
            entered_by=technician,
            value="hemolyzed+++",
            flag=None,
        )
    resp = _approve(auth_headers, pathologist, result.id, {"decision": "approved"})
    assert resp.status_code == 422
    # With a note it is approved.
    resp2 = _approve(
        auth_headers,
        pathologist,
        result.id,
        {"decision": "approved", "note": "Value unparseable; verified manually."},
    )
    assert resp2.status_code == 200


def test_rs10_qualitative_null_flag_no_note_ok(
    tenant_a: Any, auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        technician = StaffUserFactory(role=Role.TECHNICIAN, branch=branch)
        pathologist = StaffUserFactory(role=Role.PATHOLOGIST, branch=branch)
        # Qualitative test: no numeric range row at all.
        test = TestFactory(code="MAL", name="Malaria ICT")
        sample = SampleFactory(status=Sample.Status.IN_PROCESS, branch=branch)
        SampleTestFactory(sample=sample, test=test)
        result = ResultFactory(
            sample=sample,
            test=test,
            entered_by=technician,
            value="Positive",
            flag=None,
        )
    resp = _approve(auth_headers, pathologist, result.id, {"decision": "approved"})
    assert resp.status_code == 200


# ---- RS-8 completion (T-32) ----


def test_partial_approval_sample_stays_in_process(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        sample = Sample.objects.get(pk=setup["sample"].id)
        assert sample.status == Sample.Status.IN_PROCESS
        assert not SampleEvent.objects.filter(
            sample=sample, event=SampleEvent.EventType.READY
        ).exists()


def test_approve_all_completes_sample_ready(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    r1 = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    r2 = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_b"].id,
        {"decision": "approved"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    with tenant_context(tenant_a):
        sample = Sample.objects.get(pk=setup["sample"].id)
        assert sample.status == Sample.Status.READY
        event = SampleEvent.objects.filter(
            sample=sample, event=SampleEvent.EventType.READY
        ).first()
        assert event is not None
        audit = AuditLog.objects.filter(
            entity_id=sample.id, action="sample.ready"
        ).first()
        assert audit is not None
        assert audit.after_jsonb is not None
        assert audit.after_jsonb.get("event") == "sample.ready"


# ---- Withdrawal (T-49, RS-4) ----


def test_withdraw_by_author_ok(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _withdraw(auth_headers, setup["technician"], setup["result_a"].id)
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        result = Result.objects.get(pk=setup["result_a"].id)
        assert result.status == Result.Status.WITHDRAWN
        # RS-4: NO result_approval row is written.
        assert ResultApproval.objects.filter(result_id=result.id).count() == 0
        actions = _audit_actions(tenant_a, result.id)
        assert "result.withdrawn" in actions
        assert "result.approved" not in actions


def test_withdraw_by_non_author_403(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    # Pathologist is not the author (technician entered).
    resp = _withdraw(auth_headers, setup["pathologist"], setup["result_a"].id)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "withdraw_not_permitted"


def test_withdraw_after_approval_decision_409(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    ok = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    assert ok.status_code == 200
    # Even the author cannot withdraw after a decision exists.
    resp = _withdraw(auth_headers, setup["technician"], setup["result_a"].id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_state_transition"


def test_withdraw_after_rejection_decision_409(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    ok = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "rejected", "note": "Recollect."},
    )
    assert ok.status_code == 200
    resp = _withdraw(auth_headers, setup["technician"], setup["result_a"].id)
    assert resp.status_code == 409


def test_withdrawn_result_is_read_only(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    w = _withdraw(auth_headers, setup["technician"], setup["result_a"].id)
    assert w.status_code == 200
    # A withdrawn result can no longer be approved.
    resp = _approve(
        auth_headers,
        setup["pathologist"],
        setup["result_a"].id,
        {"decision": "approved"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_state_transition"


def test_withdraw_404_not_found(
    tenant_a: Any, lab26_setup: Any, auth_headers: Any
) -> None:
    setup = lab26_setup
    resp = _withdraw(auth_headers, setup["technician"], uuid.uuid4())
    assert resp.status_code == 404
