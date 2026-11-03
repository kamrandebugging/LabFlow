"""LAB-27 Test Suite: Result amendments (Doc 03 §5.5 RS-9, RS-V1, §6.6, §5.6
RP-4; KAN-152; original LAB-32).

Covers (T-33):
- POST /api/v1/results/{id}/amend — roles T/P ONLY (exact §6.6 cell "T P");
  403 for O/M/R.
- ONLY on an approved result -> 409 invalid_state_transition from entered,
  rejected, amended, withdrawn. 404 out of scope / not found.
- Body: value (required, non-empty after trim, max 500 — RS-V1), unit
  (optional), reason (REQUIRED non-empty -> 422 amend_reason_required).
  Unknown fields rejected.
- -> 201 new result row, status entered, supersedes -> old row, amend_reason
  stored, entered_by = caller. Old row NOT touched. Engine flag/qualifier
  computed (LAB-24 engine). Audit result.amendment_created linking old->new;
  event flag result.entered.
- 409 amendment_already_pending if an unapproved amendment exists.
- Approve hook (RS-9): approving an amendment REQUIRES a non-empty note ->
  422 amendment_approval_note_required (amend-time reason does NOT satisfy).
  On approval the old row becomes amended IN THE SAME TRANSACTION; event
  flag result.amended fires. Rejection of an amendment leaves the old row
  approved. No row ever edited (original value verbatim).
- Final report hook (§5.6 RP-4): if the sample has a FINAL report, the
  amendment's approval audit carries report.version_requested.
"""

import json
import uuid
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.reports.models import Report
from apps.results.models import Result
from apps.samples.models import Sample
from tests.factories.branch import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.reports import ReportFactory
from tests.factories.results import ResultFactory
from tests.factories.samples import SampleFactory, SampleTestFactory
from tests.factories.staff_user import StaffUserFactory

AMEND_URL = "/api/v1/results/{result_id}/amend"
APPROVE_URL = "/api/v1/results/{result_id}/approve"


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
def lab27_setup(tenant_a: Any) -> dict[str, Any]:
    """One in_process sample, one test, result entered by technician."""
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
        owner = StaffUserFactory(
            role=Role.OWNER, branch=branch, email="own@labflow.app"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="mgr@labflow.app"
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="rec@labflow.app"
        )
        test = TestFactory(code="GLU", name="Glucose")
        sample = SampleFactory(status=Sample.Status.IN_PROCESS, branch=branch)
        SampleTestFactory(sample=sample, test=test)
        result = ResultFactory(
            sample=sample, test=test, entered_by=technician, flag=Result.Flag.NORMAL
        )
        return {
            "branch": branch,
            "technician": technician,
            "pathologist": pathologist,
            "pathologist2": pathologist2,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "test": test,
            "sample": sample,
            "result": result,
        }


def _post(auth_headers: Any, user: Any, url: str, body: dict[str, Any]) -> Any:
    return Client().post(
        url,
        data=json.dumps(body),
        content_type="application/json",
        headers=auth_headers(user),
    )


def _approved_result(tenant_a: Any, setup: dict[str, Any], auth_headers: Any) -> Result:
    """Approve the setup's entered result via the API (pathologist)."""
    with tenant_context(tenant_a):
        result_id = setup["result"].id
    resp = _post(
        auth_headers,
        setup["pathologist"],
        APPROVE_URL.format(result_id=result_id),
        {"decision": "approved", "note": "looks good"},
    )
    assert resp.status_code == 200, resp.content[:300]
    with tenant_context(tenant_a):
        return Result.objects.get(pk=result_id)


def _amend(
    auth_headers: Any, user: Any, result_id: uuid.UUID, body: dict[str, Any]
) -> Any:
    return _post(auth_headers, user, AMEND_URL.format(result_id=result_id), body)


# ---- Happy path (T-33) ----


def test_amend_happy_path_201(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    old_value = old.value

    resp = _amend(
        auth_headers,
        setup["technician"],
        old.id,
        {"value": "102.5", "unit": "mg/dL", "reason": "recalibrated analyser"},
    )
    assert resp.status_code == 201, resp.content[:500]
    body = resp.json()

    assert body["status"] == "entered"
    assert body["value"] == "102.5"
    assert body["unit"] == "mg/dL"
    assert body["entered_by"] == str(setup["technician"].id)
    assert body["flag"] in ("low", "normal", "high", "critical", None)

    with tenant_context(tenant_a):
        new = Result.objects.get(pk=body["id"])
        assert new.supersedes_id == old.id
        assert new.amend_reason == "recalibrated analyser"
        assert new.sample_id == old.sample_id
        assert new.test_id == old.test_id
        # Old row untouched: still approved, value verbatim.
        old.refresh_from_db()
        assert old.status == Result.Status.APPROVED
        assert old.value == old_value
        # Chain link.
        assert old.amendments.count() == 1
        # Audit chain old -> new with result.entered event flag.
        audit = AuditLog.objects.get(
            action="result.amendment_created", entity_id=new.id
        )
        assert audit.after_jsonb is not None
        assert audit.after_jsonb.get("old_result_id") == str(old.id)
        assert audit.after_jsonb.get("new_result_id") == str(new.id)
        assert audit.after_jsonb.get("event") == "result.entered"


def test_amend_unit_optional_falls_back(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    resp = _amend(
        auth_headers,
        setup["pathologist"],
        old.id,
        {"value": "99.0", "reason": "repeat run"},
    )
    assert resp.status_code == 201, resp.content[:500]


# ---- Guards: state, 404, roles ----


@pytest.mark.parametrize(
    "from_status",
    [
        Result.Status.ENTERED,
        Result.Status.REJECTED,
        Result.Status.AMENDED,
        Result.Status.WITHDRAWN,
    ],
)
def test_amend_only_from_approved(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any, from_status: str
) -> None:
    setup = lab27_setup
    with tenant_context(tenant_a):
        setup["result"].status = from_status
        setup["result"].save(update_fields=["status"])
        result_id = setup["result"].id
    resp = _amend(
        auth_headers,
        setup["technician"],
        result_id,
        {"value": "1.0", "reason": "x"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_state_transition"


def test_amend_404_out_of_scope(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    resp = _amend(
        auth_headers,
        setup["technician"],
        uuid.uuid4(),
        {"value": "1.0", "reason": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("role_key", ["owner", "manager", "receptionist"])
def test_amend_roles_forbidden(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any, role_key: str
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    resp = _amend(
        auth_headers,
        setup[role_key],
        old.id,
        {"value": "1.0", "reason": "x"},
    )
    assert resp.status_code == 403


# ---- Body validation ----


def test_amend_reason_required(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    for body in ({"value": "1.0"}, {"value": "1.0", "reason": "   "}):
        resp = _amend(auth_headers, setup["technician"], old.id, body)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "amend_reason_required"


def test_amend_value_validation(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    # Missing value -> 422 (serializer).
    resp = _amend(auth_headers, setup["technician"], old.id, {"reason": "x"})
    assert resp.status_code == 422
    # Whitespace-only value -> 422 (RS-V1: non-empty after trim).
    resp = _amend(
        auth_headers, setup["technician"], old.id, {"value": "   ", "reason": "x"}
    )
    assert resp.status_code == 422
    # >500 chars -> 422 (RS-V1).
    resp = _amend(
        auth_headers,
        setup["technician"],
        old.id,
        {"value": "9" * 501, "reason": "x"},
    )
    assert resp.status_code == 422


def test_amend_unknown_fields_rejected(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    resp = _amend(
        auth_headers,
        setup["technician"],
        old.id,
        {"value": "1.0", "reason": "x", "bogus": 1},
    )
    assert resp.status_code == 422


# ---- Amendment-already-pending + constraint coexistence ----


def test_amendment_already_pending_409(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    first = _amend(
        auth_headers, setup["technician"], old.id, {"value": "1.0", "reason": "first"}
    )
    assert first.status_code == 201
    second = _amend(
        auth_headers, setup["technician"], old.id, {"value": "2.0", "reason": "second"}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "amendment_already_pending"


def test_approved_original_and_entered_amendment_coexist(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    """LAB-25 partial unique (sample, test) WHERE status='entered' must allow
    an approved original + one entered amendment (T-33 / DoD)."""
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    resp = _amend(
        auth_headers, setup["technician"], old.id, {"value": "7.7", "reason": "check"}
    )
    assert resp.status_code == 201
    with tenant_context(tenant_a):
        assert (
            Result.objects.filter(
                sample=old.sample, test=old.test, status=Result.Status.APPROVED
            ).count()
            == 1
        )
        assert (
            Result.objects.filter(
                sample=old.sample, test=old.test, status=Result.Status.ENTERED
            ).count()
            == 1
        )


# ---- Approve hook (RS-9) ----


def _approve_amendment(
    auth_headers: Any, user: Any, result_id: uuid.UUID, body: dict[str, Any]
) -> Any:
    return _post(auth_headers, user, APPROVE_URL.format(result_id=result_id), body)


def test_approve_amendment_requires_note_422(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    """RS-9: the amend-time reason does NOT satisfy the approval note."""
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    new_id = uuid.UUID(
        _amend(
            auth_headers,
            setup["technician"],
            old.id,
            {"value": "5.5", "reason": "re-run"},
        ).json()["id"]
    )
    resp = _approve_amendment(
        auth_headers, setup["pathologist"], new_id, {"decision": "approved"}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "amendment_approval_note_required"
    # Nothing changed: new still entered, old still approved.
    with tenant_context(tenant_a):
        assert Result.objects.get(pk=new_id).status == Result.Status.ENTERED
        assert Result.objects.get(pk=old.id).status == Result.Status.APPROVED


def test_approve_amendment_happy_path(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    old_value = old.value
    new_id = uuid.UUID(
        _amend(
            auth_headers,
            setup["technician"],
            old.id,
            {"value": "5.5", "reason": "re-run"},
        ).json()["id"]
    )
    resp = _approve_amendment(
        auth_headers,
        setup["pathologist"],
        new_id,
        {"decision": "approved", "note": "verified against rerun"},
    )
    assert resp.status_code == 200, resp.content[:500]
    with tenant_context(tenant_a):
        new = Result.objects.get(pk=new_id)
        assert new.status == Result.Status.APPROVED
        # Old row becomes amended IN THE SAME TRANSACTION — value verbatim.
        old.refresh_from_db()
        assert old.status == Result.Status.AMENDED
        assert old.value == old_value
        # result.amended event flag fires at the amendment's approval.
        audit = AuditLog.objects.get(action="result.approved", entity_id=new.id)
        assert audit.after_jsonb is not None
        assert audit.after_jsonb.get("event") == "result.amended"
        assert audit.after_jsonb.get("amendment_of") == str(old.id)


def test_reject_amendment_keeps_old_approved(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    new_id = uuid.UUID(
        _amend(
            auth_headers,
            setup["technician"],
            old.id,
            {"value": "5.5", "reason": "re-run"},
        ).json()["id"]
    )
    resp = _approve_amendment(
        auth_headers,
        setup["pathologist"],
        new_id,
        {"decision": "rejected", "note": "bad rerun"},
    )
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        assert Result.objects.get(pk=new_id).status == Result.Status.REJECTED
        assert Result.objects.get(pk=old.id).status == Result.Status.APPROVED


def test_original_value_never_edited(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    """DoD: no row ever edited — the original value is byte-identical."""
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    with tenant_context(tenant_a):
        before = Result.objects.get(pk=old.id).value
    new_id = uuid.UUID(
        _amend(
            auth_headers,
            setup["technician"],
            old.id,
            {"value": "5.5", "reason": "re-run"},
        ).json()["id"]
    )
    _approve_amendment(
        auth_headers,
        setup["pathologist"],
        new_id,
        {"decision": "approved", "note": "ok"},
    )
    with tenant_context(tenant_a):
        after = Result.objects.get(pk=old.id)
        assert after.value == before
        assert after.value != "5.5"


# ---- Final-report hook (§5.6 RP-4) ----


def test_amendment_approval_with_final_report_sets_version_flag(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    with tenant_context(tenant_a):
        ReportFactory(sample=setup["sample"], status=Report.Status.FINAL)
    new_id = uuid.UUID(
        _amend(
            auth_headers,
            setup["technician"],
            old.id,
            {"value": "5.5", "reason": "re-run"},
        ).json()["id"]
    )
    resp = _approve_amendment(
        auth_headers,
        setup["pathologist"],
        new_id,
        {"decision": "approved", "note": "ok"},
    )
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        audit = AuditLog.objects.get(action="result.approved", entity_id=new_id)
        assert audit.after_jsonb is not None
        assert audit.after_jsonb.get("event") == "result.amended"
        assert audit.after_jsonb.get("report_version_requested") is True


def test_amendment_approval_without_final_report_no_flag(
    tenant_a: Any, lab27_setup: Any, auth_headers: Any
) -> None:
    setup = lab27_setup
    old = _approved_result(tenant_a, setup, auth_headers)
    new_id = uuid.UUID(
        _amend(
            auth_headers,
            setup["technician"],
            old.id,
            {"value": "5.5", "reason": "re-run"},
        ).json()["id"]
    )
    _approve_amendment(
        auth_headers,
        setup["pathologist"],
        new_id,
        {"decision": "approved", "note": "ok"},
    )
    with tenant_context(tenant_a):
        audit = AuditLog.objects.get(action="result.approved", entity_id=new_id)
        assert audit.after_jsonb is not None
        assert "report_version_requested" not in audit.after_jsonb
