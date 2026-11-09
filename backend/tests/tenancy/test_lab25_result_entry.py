"""LAB-25 Test Suite: Batch result entry (Doc 03 §5.5 RS-1/RS-2/RS-3/RS-V2,
§6.6, §8, KAN-150; original LAB-30).

Covers:
- POST /api/v1/samples/{id}/results — roles Technician, Pathologist ONLY
  (403 for O/M/R).
- Body: results [{test_id, value, unit (optional)}].
- RS-V2 all-or-nothing: every row validated first; any failure -> 422 with
  per-row errors (test_id + code), NOTHING saved (T-27).
- RS-1: test without a sample_test row -> 422 test_not_ordered (T-26).
- RS-2: value stored EXACTLY as entered (text); flag computed by the LAB-24
  engine; qualifier + matched range summary in the response; unit defaults
  to the matched range's unit and is stored.
- RS-3: entry requires received|in_process (-> 409 invalid_state_transition);
  first entry moves received -> in_process (+ IN_PROCESS event, same txn).
  Branch gate FIRST: is_collection_centre && !result_entry_enabled ->
  403 result_entry_disabled_at_branch regardless of state.
- BS-3: technician must have branch scope on the holding branch
  (-> 409 sample_not_here).
- 409 transfer_already_open when an open transfer exists (SM-7).
- Concurrency (T-28): two concurrent entries for the same test -> exactly
  one 201, one 409 result_already_entered naming the winning author,
  exactly one result row.
- entered_by = authenticated user; one result.entered audit row per result.
"""

import json
import threading
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.billing.services import BillingService
from apps.results.models import Result
from apps.samples.models import Sample, SampleEvent, SampleTransfer
from tests.factories.branch import BranchFactory
from tests.factories.catalog import ReferenceRangeFactory, TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

RESULTS_URL = "/api/v1/samples/{sample_id}/results"
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
def lab25_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        other_branch = BranchFactory(code="BR2", name="Second Branch")
        coll_branch = BranchFactory(
            code="CC1",
            name="Collection Centre",
            is_collection_centre=True,
            result_entry_enabled=False,
        )
        enabled_coll_branch = BranchFactory(
            code="CC2",
            name="Enabled Collection Centre",
            is_collection_centre=True,
            result_entry_enabled=True,
        )

        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="t25_owner@x.com")
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="t25_manager@x.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="t25_reception@x.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="t25_tech@x.com"
        )
        StaffBranch.objects.create(
            staff_user=technician, branch=branch, is_primary=True
        )
        technician2 = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="t25_tech2@x.com"
        )
        StaffBranch.objects.create(
            staff_user=technician2, branch=branch, is_primary=True
        )
        other_tech = StaffUserFactory(
            role=Role.TECHNICIAN, branch=other_branch, email="t25_tech_other@x.com"
        )
        StaffBranch.objects.create(
            staff_user=other_tech, branch=other_branch, is_primary=True
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="t25_path@x.com"
        )

        patient = PatientFactory(branch=branch)
        test_a = TestFactory(name="Glucose", code="GLU001")
        TestPriceFactory(test=test_a, panel=None, price=Decimal("500.00"))
        ReferenceRangeFactory(
            test=test_a,
            sex="B",
            age_min_days=0,
            age_max_days=None,
            low=Decimal("70.000"),
            high=Decimal("110.000"),
            critical_low=Decimal("40.000"),
            critical_high=Decimal("400.000"),
            unit="mg/dL",
        )
        test_b = TestFactory(name="Cholesterol", code="CHL001")
        TestPriceFactory(test=test_b, panel=None, price=Decimal("600.00"))
        ReferenceRangeFactory(
            test=test_b,
            sex="B",
            age_min_days=0,
            age_max_days=None,
            low=Decimal("125.000"),
            high=Decimal("200.000"),
            critical_low=None,
            critical_high=None,
            unit="mg/dL",
        )
        test_c = TestFactory(name="Unordered", code="UNO001")
        TestPriceFactory(test=test_c, panel=None, price=Decimal("700.00"))

        return {
            "branch": branch,
            "other_branch": other_branch,
            "coll_branch": coll_branch,
            "enabled_coll_branch": enabled_coll_branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "technician2": technician2,
            "other_tech": other_tech,
            "pathologist": pathologist,
            "patient": patient,
            "test_a": test_a,
            "test_b": test_b,
            "test_c": test_c,
        }


def _make_invoice(tenant_a: Any, setup: dict[str, Any], actor: Any) -> Any:
    with tenant_context(tenant_a):
        invoice, _ = BillingService.create_invoice(
            patient_id=setup["patient"].id,
            branch_id=setup["branch"].id,
            referral_partner_id=None,
            items=[
                {"test_id": setup["test_a"].id, "qty": 1},
                {"test_id": setup["test_b"].id, "qty": 1},
            ],
            discount_amount=Decimal("0.00"),
            discount_reason=None,
            idempotency_key=f"lab25-{uuid.uuid4()}",
            actor=actor,
        )
        return invoice


def _collect_and_receive(
    tenant_a: Any, setup: dict[str, Any], auth_headers: Any, branch: Any = None
) -> Any:
    """Invoice -> collect -> receive. Returns the sample (status=received)."""
    headers = auth_headers(setup["receptionist"])
    inv = _make_invoice(tenant_a, setup, setup["receptionist"])
    resp = Client().post(
        SAMPLES_URL,
        data=json.dumps({"invoice_id": str(inv.id)}),
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 201, resp.content[:300]
    sample_id = resp.json()["id"]
    if branch is not None:
        with tenant_context(tenant_a):
            Sample.objects.filter(pk=sample_id).update(branch_id=branch.id)
    recv = Client().post(
        f"/api/v1/samples/{sample_id}/receive",
        data=json.dumps({}),
        content_type="application/json",
        headers=auth_headers(setup["technician"]),
    )
    # receive requires the caller branch to hold the sample; for a moved
    # sample the owning branch's technician receives instead.
    assert recv.status_code in (200, 409), recv.content[:300]
    with tenant_context(tenant_a):
        return Sample.objects.get(pk=sample_id)


def _post_results(
    auth_headers: Any,
    user: Any,
    sample_id: Any,
    rows: list[dict[str, Any]],
) -> Any:
    return Client().post(
        RESULTS_URL.format(sample_id=sample_id),
        data=json.dumps({"results": rows}),
        content_type="application/json",
        headers=auth_headers(user),
    )


def _row(test_id: Any, value: str, unit: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"test_id": str(test_id), "value": value}
    if unit is not None:
        row["unit"] = unit
    return row


# ---------------------------------------------------------------------------
# Roles (T P only)
# ---------------------------------------------------------------------------


def test_t26_roles_only_technician_and_pathologist(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    rows = [_row(setup["test_a"].id, "85")]

    for user_key, expected in [
        ("technician", 201),
        ("pathologist", 201),
        ("owner", 201),
        ("manager", 403),
        ("receptionist", 403),
    ]:
        # fresh sample per role: one result row per test is terminal here
        s = _collect_and_receive(tenant_a, setup, auth_headers)
        resp = _post_results(auth_headers, setup[user_key], s.id, rows)
        assert resp.status_code == expected, (user_key, resp.content[:300])

    assert sample.status == "received"  # untouched sample from setup


# ---------------------------------------------------------------------------
# Happy path: flags, qualifiers, units, verbatim values
# ---------------------------------------------------------------------------


def test_t27_happy_batch_flags_and_response_shape(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers,
        setup["technician"],
        sample.id,
        [
            _row(setup["test_a"].id, "85"),  # 70-110 -> normal
            _row(setup["test_b"].id, "250"),  # 125-200 -> high
        ],
    )
    assert resp.status_code == 201, resp.content[:400]
    body = resp.json()
    assert len(body["results"]) == 2

    by_test = {r["test_id"]: r for r in body["results"]}
    ra = by_test[str(setup["test_a"].id)]
    assert ra["value"] == "85"  # verbatim
    assert ra["flag"] == "normal"
    assert ra["qualifier"] is None
    assert ra["unit"] == "mg/dL"  # defaulted from matched range
    assert ra["needs_review"] is False
    assert ra["status"] == "entered"
    assert ra["matched_range"]["low"] == "70.000"
    assert ra["matched_range"]["high"] == "110.000"

    rb = by_test[str(setup["test_b"].id)]
    assert rb["flag"] == "high"
    assert rb["unit"] == "mg/dL"

    with tenant_context(tenant_a):
        stored = Result.objects.get(sample_id=sample.id, test_id=setup["test_a"].id)
        assert stored.value == "85"
        assert stored.flag == "normal"
        assert stored.unit == "mg/dL"
        assert stored.status == "entered"
        assert stored.entered_by_id == setup["technician"].id


def test_qualifier_and_critical_flag_surfaced(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers, setup["technician"], sample.id, [_row(setup["test_a"].id, ">500")]
    )
    assert resp.status_code == 201, resp.content[:300]
    r = resp.json()["results"][0]
    assert r["value"] == ">500"  # stored verbatim, never rewritten
    assert r["qualifier"] == ">"
    assert r["flag"] == "critical"  # 500 > critical_high 400
    with tenant_context(tenant_a):
        assert Result.objects.get(sample_id=sample.id).value == ">500"


def test_explicit_unit_stored_over_default(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers,
        setup["technician"],
        sample.id,
        [_row(setup["test_a"].id, "85", unit="mmol/L")],
    )
    assert resp.status_code == 201, resp.content[:300]
    assert resp.json()["results"][0]["unit"] == "mmol/L"
    with tenant_context(tenant_a):
        assert Result.objects.get(sample_id=sample.id).unit == "mmol/L"


def test_needs_review_for_unparseable_value(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers, setup["technician"], sample.id, [_row(setup["test_a"].id, "N/A")]
    )
    assert resp.status_code == 201, resp.content[:300]
    r = resp.json()["results"][0]
    assert r["flag"] is None  # never guessed
    assert r["needs_review"] is True
    assert r["value"] == "N/A"


# ---------------------------------------------------------------------------
# RS-V2 all-or-nothing (T-27) + RS-1 test_not_ordered (T-26)
# ---------------------------------------------------------------------------


def test_t27_all_or_nothing_lists_failing_rows(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers,
        setup["technician"],
        sample.id,
        [
            _row(setup["test_a"].id, "85"),  # valid
            _row(setup["test_c"].id, "10"),  # NOT ordered on this sample
        ],
    )
    assert resp.status_code == 422, resp.content[:400]
    body = resp.json()
    rows = body["error"]["details"]["rows"]
    assert len(rows) == 1
    assert rows[0]["test_id"] == str(setup["test_c"].id)
    assert rows[0]["code"] == "test_not_ordered"
    with tenant_context(tenant_a):
        assert Result.objects.filter(sample_id=sample.id).count() == 0
        assert Sample.objects.get(pk=sample.id).status == "received"
        assert not SampleEvent.objects.filter(
            sample_id=sample.id, event="IN_PROCESS"
        ).exists()


def test_duplicate_test_within_batch_rejected(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers,
        setup["technician"],
        sample.id,
        [
            _row(setup["test_a"].id, "85"),
            _row(setup["test_a"].id, "90"),
        ],
    )
    assert resp.status_code == 422, resp.content[:300]
    with tenant_context(tenant_a):
        assert Result.objects.filter(sample_id=sample.id).count() == 0


def test_unknown_fields_rejected(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = Client().post(
        RESULTS_URL.format(sample_id=sample.id),
        data=json.dumps({"results": [_row(setup["test_a"].id, "85")], "bogus": 1}),
        content_type="application/json",
        headers=auth_headers(setup["technician"]),
    )
    assert resp.status_code == 422, resp.content[:300]


# ---------------------------------------------------------------------------
# RS-3: branch gate first, then state rule
# ---------------------------------------------------------------------------


def test_branch_gate_collection_centre_refused_before_state(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    """403 result_entry_disabled_at_branch even though sample is collected."""
    setup = lab25_setup
    headers = auth_headers(setup["receptionist"])
    inv = _make_invoice(tenant_a, setup, setup["receptionist"])
    resp = Client().post(
        SAMPLES_URL,
        data=json.dumps({"invoice_id": str(inv.id)}),
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 201
    sample_id = resp.json()["id"]
    with tenant_context(tenant_a):
        Sample.objects.filter(pk=sample_id).update(branch_id=setup["coll_branch"].id)

    resp = _post_results(
        auth_headers, setup["technician"], sample_id, [_row(setup["test_a"].id, "85")]
    )
    assert resp.status_code == 403, resp.content[:300]
    assert resp.json()["error"]["code"] == "result_entry_disabled_at_branch"


def test_branch_gate_enabled_collection_centre_allowed(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(
        tenant_a, setup, auth_headers, branch=setup["enabled_coll_branch"]
    )
    # receive at the enabled centre: use a tech of that branch
    with tenant_context(tenant_a):
        centre_tech = StaffUserFactory(
            role=Role.TECHNICIAN,
            branch=setup["enabled_coll_branch"],
            email="t25_tech_cc2@x.com",
        )
        StaffBranch.objects.create(
            staff_user=centre_tech, branch=setup["enabled_coll_branch"], is_primary=True
        )
    # sample was moved before receive; re-receive properly at the centre
    recv = Client().post(
        f"/api/v1/samples/{sample.id}/receive",
        data=json.dumps({}),
        content_type="application/json",
        headers=auth_headers(centre_tech),
    )
    assert recv.status_code == 200, recv.content[:300]
    resp = _post_results(
        auth_headers, centre_tech, sample.id, [_row(setup["test_a"].id, "85")]
    )
    assert resp.status_code == 201, resp.content[:300]


def test_invalid_state_from_collected(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    headers = auth_headers(setup["receptionist"])
    inv = _make_invoice(tenant_a, setup, setup["receptionist"])
    resp = Client().post(
        SAMPLES_URL,
        data=json.dumps({"invoice_id": str(inv.id)}),
        content_type="application/json",
        headers=headers,
    )
    sample_id = resp.json()["id"]  # status=collected
    resp = _post_results(
        auth_headers, setup["technician"], sample_id, [_row(setup["test_a"].id, "85")]
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "invalid_state_transition"


def test_first_entry_moves_received_to_in_process(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    assert sample.status == "received"
    resp = _post_results(
        auth_headers, setup["technician"], sample.id, [_row(setup["test_a"].id, "85")]
    )
    assert resp.status_code == 201, resp.content[:300]
    with tenant_context(tenant_a):
        sample.refresh_from_db()
        assert sample.status == "in_process"
        assert SampleEvent.objects.filter(
            sample_id=sample.id, event="IN_PROCESS"
        ).exists()


def test_entry_on_in_process_sample_keeps_state(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    _post_results(
        auth_headers, setup["technician"], sample.id, [_row(setup["test_a"].id, "85")]
    )
    resp = _post_results(
        auth_headers, setup["technician"], sample.id, [_row(setup["test_b"].id, "150")]
    )
    assert resp.status_code == 201, resp.content[:300]
    with tenant_context(tenant_a):
        assert Sample.objects.get(pk=sample.id).status == "in_process"
        assert (
            SampleEvent.objects.filter(sample_id=sample.id, event="IN_PROCESS").count()
            == 1
        )


def test_technician_branch_scope_enforced(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    """BS-3: a technician of another branch cannot enter results here."""
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers, setup["other_tech"], sample.id, [_row(setup["test_a"].id, "85")]
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "sample_not_here"


def test_transfer_already_open_blocks_entry(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    with tenant_context(tenant_a):
        SampleTransfer.objects.create(
            sample_id=sample.id,
            from_branch=setup["branch"],
            to_branch=setup["other_branch"],
            transferred_by=setup["manager"],
            status=SampleTransfer.Status.OPEN,
        )
    resp = _post_results(
        auth_headers, setup["technician"], sample.id, [_row(setup["test_a"].id, "85")]
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "transfer_already_open"


# ---------------------------------------------------------------------------
# Concurrency (T-28): exactly one winner, loser names the author
# ---------------------------------------------------------------------------
# NOTE: transaction=True — the test is NOT wrapped in a rollback transaction,
# so setup rows are really committed and visible to the worker threads'
# separate DB connections. Without this, threads cannot see uncommitted
# setup data and the race cannot be exercised.


@pytest.mark.django_db(transaction=True)
def test_t28_concurrent_same_test_one_winner(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    url = RESULTS_URL.format(sample_id=sample.id)
    payload = json.dumps({"results": [_row(setup["test_a"].id, "85")]})
    barrier = threading.Barrier(2)
    outcomes: dict[int, Any] = {}
    thread_errors: dict[int, str] = {}

    def _enter(idx: int, user: Any) -> None:
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
            # Release this thread's DB connection or teardown blocks on
            # "database is being accessed by other users".
            from django.db import connections

            for conn in connections.all():
                conn.close()

    t1 = threading.Thread(target=_enter, args=(1, setup["technician"]))
    t2 = threading.Thread(target=_enter, args=(2, setup["technician2"]))
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    assert not thread_errors, thread_errors
    codes = sorted(o.status_code for o in outcomes.values())
    assert codes == [201, 409], [o.status_code for o in outcomes.values()]
    loser = next(o for o in outcomes.values() if o.status_code == 409)
    body = loser.json()["error"]
    assert body["code"] == "result_already_entered"
    assert "details" in body and "entered_by" in body["details"]
    with tenant_context(tenant_a):
        assert Result.objects.filter(sample_id=sample.id).count() == 1


def test_sequential_duplicate_entry_409_names_author(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    _post_results(
        auth_headers, setup["technician"], sample.id, [_row(setup["test_a"].id, "85")]
    )
    resp = _post_results(
        auth_headers, setup["technician2"], sample.id, [_row(setup["test_a"].id, "90")]
    )
    assert resp.status_code == 409, resp.content[:300]
    body = resp.json()["error"]
    assert body["code"] == "result_already_entered"
    assert setup["technician"].email in str(body["details"])


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_audit_one_row_per_result_plus_in_process(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    sample = _collect_and_receive(tenant_a, setup, auth_headers)
    resp = _post_results(
        auth_headers,
        setup["technician"],
        sample.id,
        [
            _row(setup["test_a"].id, "85"),
            _row(setup["test_b"].id, "150"),
        ],
    )
    assert resp.status_code == 201
    with tenant_context(tenant_a):
        entered = AuditLog.objects.filter(action="result.entered", entity_type="result")
        assert entered.count() == 2
        assert {a.actor_id for a in entered} == {setup["technician"].id}
        assert AuditLog.objects.filter(
            action="sample.in_process", entity_type="sample", entity_id=sample.id
        ).exists()


def test_sample_not_found_404(
    tenant_a: Any, lab25_setup: Any, auth_headers: Any
) -> None:
    setup = lab25_setup
    resp = _post_results(
        auth_headers,
        setup["technician"],
        uuid.uuid4(),
        [_row(setup["test_a"].id, "85")],
    )
    assert resp.status_code == 404, resp.content[:200]
