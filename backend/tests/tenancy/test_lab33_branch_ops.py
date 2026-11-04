"""LAB-33 Test Suite: Branch operations (Doc 04 §8.2, §8.3, §11.3, KAN-158).

Covers (original LAB-44, backend only — five endpoints):
- TN-18: branch code change after a patient exists → 422 branch_code_immutable;
  unreferenced branch → code change allowed; format enforced (§8.2).
- TN-22: close with an open transfer → 409 branch_has_open_work with counts;
  clean close → 200 + deleted_at; reopen restores (→ 200, deleted_at cleared).
- TN-29: max_branches at limit → 409 plan_limit_reached with count + limit;
  collection centres count; closing frees a slot; two concurrent creates for
  the last slot → exactly one succeeds (§11.3).
- GET /api/v1/branches: excludes closed by default; ?include_closed=true is
  owner-only (others → 403).
- POST /api/v1/branches: happy 201, duplicate code 409, bad code 422.
- PATCH /api/v1/branches/{id}: happy 200, If-Match 409 on stale / 200 on fresh.
- POST .../close, POST .../reopen: happy + idempotent re-close / re-open.
- Roles: O/M/R/T/P may list; only O may write (others → 403 on every write).
- Tenant scoping: another tenant's branch id → 404, not 403.
- Audit: branch.created / branch.updated (field-level before/after) /
  branch.closed / branch.reopened, each in the same transaction as the write.
"""

import json
import threading
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.branches.models import Branch
from apps.core.models import Subscription
from apps.patients.models import Patient
from apps.samples.models import Sample, SampleTransfer
from tests.factories.branch import BranchFactory
from tests.factories.core import PlanFactory
from tests.factories.patients import PatientFactory
from tests.factories.samples import SampleFactory, SampleTransferFactory
from tests.factories.staff_user import StaffUserFactory

BRANCHES_URL = "/api/v1/branches"


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
def lab33_setup(tenant_a: Any) -> dict[str, Any]:
    """One open branch, one closed branch, one user per role."""
    with tenant_context(tenant_a):
        main = BranchFactory(code="M01", name="Main Laboratory")
        closed = BranchFactory(
            code="C01",
            name="Closed Branch",
            deleted_at=timezone.now() - timedelta(days=3),
        )

        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="br_owner@tenant.com"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=main, email="br_manager@tenant.com"
        )
        StaffBranch.objects.create(staff_user=manager, branch=main, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=main, email="br_reception@tenant.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=main, is_primary=True
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=main, email="br_tech@tenant.com"
        )
        StaffBranch.objects.create(staff_user=technician, branch=main, is_primary=True)
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=None, email="br_path@tenant.com"
        )
        return {
            "tenant": tenant_a,
            "main": main,
            "closed": closed,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "pathologist": pathologist,
        }


def _post_json(
    auth_headers: Any,
    user: StaffUser,
    url: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    headers = auth_headers(user)
    if extra_headers:
        headers.update(extra_headers)
    return Client().post(
        url,
        data=json.dumps(payload or {}),
        content_type="application/json",
        headers=headers,
    )


def _patch_json(
    auth_headers: Any,
    user: StaffUser,
    url: str,
    payload: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
) -> Any:
    headers = auth_headers(user)
    if extra_headers:
        headers.update(extra_headers)
    return Client().patch(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        headers=headers,
    )


def _make_plan(tenant: Any, max_branches: int | None) -> Any:
    """Public-schema plan + active subscription for the test tenant."""
    plan = PlanFactory(name=f"Tier-{uuid.uuid4().hex[:8]}", max_branches=max_branches)
    # Idempotent: conftest already provisions an ACTIVE subscription per
    # tenant; creating a second one violates uq_subscription_one_active_per_tenant.
    Subscription.objects.update_or_create(
        tenant=tenant,
        defaults={"plan": plan, "status": Subscription.Status.ACTIVE},
    )
    return plan


# ---------------------------------------------------------------------------
# GET /api/v1/branches — list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role_key", ["owner", "manager", "receptionist", "technician", "pathologist"]
)
def test_list_all_roles_200_excludes_closed(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, role_key: str
) -> None:
    setup = lab33_setup
    resp = Client().get(BRANCHES_URL, headers=auth_headers(setup[role_key]))
    assert resp.status_code == 200, resp.content[:300]
    body = resp.json()
    assert isinstance(body, list)
    codes = {b["code"] for b in body}
    assert "M01" in codes
    assert "C01" not in codes  # closed excluded by default
    row = next(b for b in body if b["code"] == "M01")
    assert set(row.keys()) >= {
        "id",
        "code",
        "name",
        "address",
        "phone",
        "is_collection_centre",
        "result_entry_enabled",
        "deleted_at",
    }
    assert row["deleted_at"] is None


def test_list_include_closed_owner_only(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = Client().get(
        BRANCHES_URL + "?include_closed=true",
        headers=auth_headers(setup["owner"]),
    )
    assert resp.status_code == 200, resp.content[:300]
    codes = {b["code"] for b in resp.json()}
    assert {"M01", "C01"} <= codes
    closed_row = next(b for b in resp.json() if b["code"] == "C01")
    assert closed_row["deleted_at"] is not None


@pytest.mark.parametrize(
    "role_key", ["manager", "receptionist", "technician", "pathologist"]
)
def test_list_include_closed_non_owner_403(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, role_key: str
) -> None:
    """Doc 04 §15 table marks include_closed '(O only)' — explicit 403, not silent."""
    setup = lab33_setup
    resp = Client().get(
        BRANCHES_URL + "?include_closed=true",
        headers=auth_headers(setup[role_key]),
    )
    assert resp.status_code == 403, resp.content[:300]
    assert resp.json()["error"]["code"] == "forbidden"


def test_list_unauthenticated_401(tenant_a: Any, lab33_setup: Any) -> None:
    resp = Client().get(BRANCHES_URL, headers={"Host": "tenant-a.localhost"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/branches — create
# ---------------------------------------------------------------------------


def test_create_happy_201_and_audit(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    payload = {
        "code": "LHR",
        "name": "Lahore Gulberg",
        "address": "Main Blvd",
        "phone": "+92423571111",
        "is_collection_centre": True,
    }
    resp = _post_json(auth_headers, setup["owner"], BRANCHES_URL, payload)
    assert resp.status_code == 201, resp.content[:300]
    body = resp.json()
    assert body["code"] == "LHR"
    assert body["name"] == "Lahore Gulberg"
    assert body["is_collection_centre"] is True
    assert body["result_entry_enabled"] is False
    assert body["deleted_at"] is None
    with tenant_context(tenant_a):
        branch = Branch.objects.get(code="LHR")
        audit = AuditLog.objects.get(action="branch.created", entity_id=branch.id)
        assert audit.actor_id == setup["owner"].id
        assert audit.entity_type == "branch"


def test_create_defaults(tenant_a: Any, lab33_setup: Any, auth_headers: Any) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "D01", "name": "D Branch"}
    )
    assert resp.status_code == 201, resp.content[:300]
    body = resp.json()
    assert body["is_collection_centre"] is False
    assert body["address"] is None
    assert body["phone"] is None


@pytest.mark.parametrize(
    "bad_code", ["lh1", "LH", "LHR1", "L R", "L-R", "", "12", "abcd", "LHR "]
)
def test_create_bad_code_422(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, bad_code: str
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers,
        setup["owner"],
        BRANCHES_URL,
        {"code": bad_code, "name": "Bad"},
    )
    assert resp.status_code == 422, resp.content[:300]
    assert resp.json()["error"]["code"] == "invalid_branch_code"


def test_create_duplicate_code_409(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "M01", "name": "Dup"}
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "duplicate_branch_code"


def test_create_duplicate_closed_code_409(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """uq_branch_code is not partial — a closed branch's code stays reserved."""
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "C01", "name": "Dup"}
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "duplicate_branch_code"


def test_create_missing_fields_422(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _post_json(auth_headers, setup["owner"], BRANCHES_URL, {"name": "No code"})
    assert resp.status_code == 422, resp.content[:300]


def test_create_unknown_field_422_strict(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers,
        setup["owner"],
        BRANCHES_URL,
        {"code": "S01", "name": "Strict", "bogus": 1},
    )
    assert resp.status_code == 422, resp.content[:300]


@pytest.mark.parametrize(
    "role_key", ["manager", "receptionist", "technician", "pathologist"]
)
def test_create_non_owner_403(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, role_key: str
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers,
        setup[role_key],
        BRANCHES_URL,
        {"code": "X01", "name": "Nope"},
    )
    assert resp.status_code == 403, resp.content[:300]
    assert resp.json()["error"]["code"] == "forbidden"


# ---------------------------------------------------------------------------
# POST — plan limit (TN-29)
# ---------------------------------------------------------------------------


def test_plan_limit_409_with_count_and_limit(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    # setup has 1 active branch (M01); limit 2 → one create OK, next 409.
    _make_plan(tenant_a, max_branches=2)
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "P01", "name": "P1"}
    )
    assert resp.status_code == 201, resp.content[:300]
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "P02", "name": "P2"}
    )
    assert resp.status_code == 409, resp.content[:300]
    body = resp.json()["error"]
    assert body["code"] == "plan_limit_reached"
    assert body["details"]["count"] == 2
    assert body["details"]["limit"] == 2


def test_plan_limit_centres_count(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Doc 04 §11.3: collection centres count — a site holds staff/samples/scope."""
    setup = lab33_setup
    _make_plan(tenant_a, max_branches=2)
    resp = _post_json(
        auth_headers,
        setup["owner"],
        BRANCHES_URL,
        {"code": "C11", "name": "Centre", "is_collection_centre": True},
    )
    assert resp.status_code == 201, resp.content[:300]
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "C12", "name": "Over"}
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "plan_limit_reached"


def test_plan_limit_unlimited_when_null(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    _make_plan(tenant_a, max_branches=None)
    setup = lab33_setup
    for code in ("U01", "U02", "U03"):
        resp = _post_json(
            auth_headers, setup["owner"], BRANCHES_URL, {"code": code, "name": code}
        )
        assert resp.status_code == 201, resp.content[:300]


def test_plan_limit_no_subscription_means_unlimited(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Interim: a tenant with no active subscription is not blocked."""
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "N01", "name": "N1"}
    )
    assert resp.status_code == 201, resp.content[:300]


def test_close_frees_a_plan_slot(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-29: closing frees a slot — the next create succeeds again."""
    setup = lab33_setup
    _make_plan(tenant_a, max_branches=2)
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "F01", "name": "F1"}
    )
    assert resp.status_code == 201, resp.content[:300]
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "F02", "name": "F2"}
    )
    assert resp.status_code == 409, resp.content[:300]
    close_resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert close_resp.status_code == 200, close_resp.content[:300]
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "F03", "name": "F3"}
    )
    assert resp.status_code == 201, resp.content[:300]


# NOTE: transaction=True — the test is NOT wrapped in a rollback transaction,
# so setup rows are really committed and visible to the worker threads'
# separate DB connections. Without this, threads cannot see uncommitted
# setup data and the race cannot be exercised.
@pytest.mark.django_db(transaction=True)
def test_tn29_concurrent_creates_last_slot_one_winner(
    tenant_a: Any, auth_headers: Any
) -> None:
    """TN-29: two concurrent creates racing the last slot → exactly one 201."""
    with tenant_context(tenant_a):
        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="race@tenant.com")
    plan = _make_plan(tenant_a, max_branches=1)
    sub = Subscription.objects.get(tenant=tenant_a, status=Subscription.Status.ACTIVE)

    headers = auth_headers(owner)
    barrier = threading.Barrier(2)
    outcomes: dict[int, Any] = {}
    thread_errors: dict[int, str] = {}

    def _create(idx: int, code: str) -> None:
        try:
            barrier.wait(timeout=15)
            outcomes[idx] = Client().post(
                BRANCHES_URL,
                data=json.dumps({"code": code, "name": f"Racer {idx}"}),
                content_type="application/json",
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced below on failure
            thread_errors[idx] = repr(exc)
        finally:
            from django.db import connections

            for conn in connections.all():
                conn.close()

    t1 = threading.Thread(target=_create, args=(1, "R01"))
    t2 = threading.Thread(target=_create, args=(2, "R02"))
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    try:
        assert not thread_errors, thread_errors
        codes = sorted(o.status_code for o in outcomes.values())
        assert codes == [201, 409], [o.status_code for o in outcomes.values()]
        loser = next(o for o in outcomes.values() if o.status_code == 409)
        body = loser.json()["error"]
        assert body["code"] == "plan_limit_reached"
        assert body["details"]["count"] == 1
        assert body["details"]["limit"] == 1
        with tenant_context(tenant_a):
            assert Branch.objects.filter(deleted_at__isnull=True).count() == 1
    finally:
        # Public-schema rows are NOT rolled back under transaction=True.
        sub.delete()
        plan.delete()


# ---------------------------------------------------------------------------
# PATCH /api/v1/branches/{id} — update
# ---------------------------------------------------------------------------


def test_patch_happy_200_and_field_audit(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    url = f"{BRANCHES_URL}/{setup['main'].id}"
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        url,
        {
            "name": "Main Renamed",
            "address": "New Address",
            "phone": "+92420000000",
            "is_collection_centre": True,
        },
    )
    assert resp.status_code == 200, resp.content[:300]
    body = resp.json()
    assert body["name"] == "Main Renamed"
    assert body["address"] == "New Address"
    assert body["is_collection_centre"] is True
    with tenant_context(tenant_a):
        audit = AuditLog.objects.filter(
            action="branch.updated", entity_id=setup["main"].id
        ).latest("at")
        assert audit.actor_id == setup["owner"].id
        assert audit.before_jsonb is not None
        assert audit.after_jsonb is not None
        assert audit.before_jsonb["name"] == "Main Laboratory"
        assert audit.after_jsonb["name"] == "Main Renamed"
        assert audit.before_jsonb["is_collection_centre"] is False
        assert audit.after_jsonb["is_collection_centre"] is True


def test_patch_partial_ok(tenant_a: Any, lab33_setup: Any, auth_headers: Any) -> None:
    setup = lab33_setup
    url = f"{BRANCHES_URL}/{setup['main'].id}"
    resp = _patch_json(auth_headers, setup["owner"], url, {"phone": "+92421111111"})
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json()["phone"] == "+92421111111"
    assert resp.json()["name"] == "Main Laboratory"


def test_patch_unknown_field_422_strict(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    url = f"{BRANCHES_URL}/{setup['main'].id}"
    resp = _patch_json(auth_headers, setup["owner"], url, {"bogus": "x"})
    assert resp.status_code == 422, resp.content[:300]


def test_patch_missing_branch_404(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _patch_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{uuid.uuid4()}", {"name": "X"}
    )
    assert resp.status_code == 404, resp.content[:300]
    assert resp.json()["error"]["code"] == "not_found"


def test_patch_cross_tenant_branch_404(
    tenant_a: Any, tenant_b: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Tenant scoping: another tenant's branch id → 404, never 403."""
    setup = lab33_setup
    with tenant_context(tenant_b):
        foreign = BranchFactory(code="F01", name="Foreign")
    resp = _patch_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{foreign.id}", {"name": "X"}
    )
    assert resp.status_code == 404, resp.content[:300]


@pytest.mark.parametrize(
    "role_key", ["manager", "receptionist", "technician", "pathologist"]
)
def test_patch_non_owner_403(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, role_key: str
) -> None:
    setup = lab33_setup
    resp = _patch_json(
        auth_headers,
        setup[role_key],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"name": "Nope"},
    )
    assert resp.status_code == 403, resp.content[:300]
    assert resp.json()["error"]["code"] == "forbidden"


# ---------------------------------------------------------------------------
# PATCH — branch code rules (TN-18, Doc 04 §8.2)
# ---------------------------------------------------------------------------


def test_tn18_code_change_after_patient_exists_422(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-18: code is immutable once any patient references the branch."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        PatientFactory(branch=setup["main"])
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"code": "N99"},
    )
    assert resp.status_code == 422, resp.content[:300]
    assert resp.json()["error"]["code"] == "branch_code_immutable"
    with tenant_context(tenant_a):
        assert Branch.objects.get(id=setup["main"].id).code == "M01"


def test_tn18_code_change_after_sample_exists_422(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-18: code is immutable once any sample references the branch."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        SampleFactory(branch=setup["main"])
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"code": "N99"},
    )
    assert resp.status_code == 422, resp.content[:300]
    assert resp.json()["error"]["code"] == "branch_code_immutable"


def test_tn18_code_change_before_any_reference_allowed(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-18: an unreferenced branch MAY accept a code change."""
    setup = lab33_setup
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"code": "N99"},
    )
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json()["code"] == "N99"
    with tenant_context(tenant_a):
        audit = AuditLog.objects.filter(
            action="branch.updated", entity_id=setup["main"].id
        ).latest("at")
        assert audit.before_jsonb is not None
        assert audit.after_jsonb is not None
        assert audit.before_jsonb["code"] == "M01"
        assert audit.after_jsonb["code"] == "N99"


def test_tn18_code_change_format_enforced(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-18: format is enforced even on an unreferenced branch."""
    setup = lab33_setup
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"code": "bad"},
    )
    assert resp.status_code == 422, resp.content[:300]
    assert resp.json()["error"]["code"] == "invalid_branch_code"


def test_tn18_code_change_duplicate_409(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"code": "C01"},
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "duplicate_branch_code"


# ---------------------------------------------------------------------------
# PATCH — If-Match (Doc 03 §6.1, version_conflict 409)
# ---------------------------------------------------------------------------


def test_patch_if_match_fresh_200(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    with tenant_context(tenant_a):
        etag = Branch.objects.get(id=setup["main"].id).updated_at.isoformat()
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"name": "Match OK"},
        extra_headers={"If-Match": etag},
    )
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json()["name"] == "Match OK"


def test_patch_if_match_stale_409(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    with tenant_context(tenant_a):
        stale = Branch.objects.get(id=setup["main"].id).updated_at.isoformat()
    # A concurrent write moves updated_at forward.
    first = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"name": "Concurrent write"},
    )
    assert first.status_code == 200
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"name": "Stale write"},
        extra_headers={"If-Match": stale},
    )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "version_conflict"


# ---------------------------------------------------------------------------
# POST /api/v1/branches/{id}/close (TN-22, Doc 04 §8.3)
# ---------------------------------------------------------------------------


def test_close_happy_200_and_audit(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json()["deleted_at"] is not None
    with tenant_context(tenant_a):
        assert Branch.objects.get(id=setup["main"].id).deleted_at is not None
        audit = AuditLog.objects.get(action="branch.closed", entity_id=setup["main"].id)
        assert audit.actor_id == setup["owner"].id
        assert audit.before_jsonb is not None
        assert audit.after_jsonb is not None
        assert audit.before_jsonb["deleted_at"] is None
        assert audit.after_jsonb["deleted_at"] is not None
    # Closed branch now hidden from the default list.
    listed = Client().get(BRANCHES_URL, headers=auth_headers(setup["owner"]))
    assert "M01" not in {b["code"] for b in listed.json()}


def test_close_idempotent_200(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Closing an already-closed branch → 200 (state guard, no error)."""
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['closed'].id}/close"
    )
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json()["deleted_at"] is not None
    with tenant_context(tenant_a):
        assert (
            AuditLog.objects.filter(
                action="branch.closed", entity_id=setup["closed"].id
            ).count()
            == 0
        )


def test_tn22_close_with_open_transfer_409_with_counts(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-22: open transfer in or out blocks the close, with counts."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        other = BranchFactory(code="O01", name="Other")
        sample = SampleFactory(branch=setup["main"])
        SampleTransferFactory(
            sample=sample,
            from_branch=setup["main"],
            to_branch=other,
            status=SampleTransfer.Status.OPEN,
        )
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert resp.status_code == 409, resp.content[:300]
    body = resp.json()["error"]
    assert body["code"] == "branch_has_open_work"
    assert body["details"]["open_transfers_out"] == 1
    assert body["details"]["open_transfers_in"] == 0
    with tenant_context(tenant_a):
        assert Branch.objects.get(id=setup["main"].id).deleted_at is None


def test_tn22_close_with_open_transfer_in_409(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    with tenant_context(tenant_a):
        other = BranchFactory(code="O02", name="Other")
        sample = SampleFactory(branch=other)
        SampleTransferFactory(
            sample=sample,
            from_branch=other,
            to_branch=setup["main"],
            status=SampleTransfer.Status.OPEN,
        )
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert resp.status_code == 409, resp.content[:300]
    body = resp.json()["error"]
    assert body["code"] == "branch_has_open_work"
    assert body["details"]["open_transfers_in"] == 1


@pytest.mark.parametrize(
    "sample_status",
    [Sample.Status.COLLECTED, Sample.Status.RECEIVED, Sample.Status.IN_PROCESS],
)
def test_tn22_close_with_held_samples_409_with_counts(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, sample_status: str
) -> None:
    """TN-22: samples held in collected|received|in_process block the close."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        SampleFactory(branch=setup["main"], status=sample_status)
        SampleFactory(branch=setup["main"], status=sample_status)
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert resp.status_code == 409, resp.content[:300]
    body = resp.json()["error"]
    assert body["code"] == "branch_has_open_work"
    assert body["details"]["samples_held"] == 2


@pytest.mark.parametrize(
    "sample_status",
    [Sample.Status.READY, Sample.Status.REJECTED, Sample.Status.CANCELLED],
)
def test_close_with_terminal_samples_ok(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, sample_status: str
) -> None:
    """Terminal samples (ready/rejected/cancelled) do not block the close."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        SampleFactory(branch=setup["main"], status=sample_status)
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert resp.status_code == 200, resp.content[:300]


def test_close_with_received_transfer_ok(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Non-open transfers (received/cancelled/lost) do not block the close."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        other = BranchFactory(code="O03", name="Other")
        sample = SampleFactory(branch=setup["main"], status=Sample.Status.READY)
        SampleTransferFactory(
            sample=sample,
            from_branch=setup["main"],
            to_branch=other,
            status=SampleTransfer.Status.RECEIVED,
        )
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert resp.status_code == 200, resp.content[:300]


def test_close_missing_branch_404(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{uuid.uuid4()}/close"
    )
    assert resp.status_code == 404, resp.content[:300]


@pytest.mark.parametrize(
    "role_key", ["manager", "receptionist", "technician", "pathologist"]
)
def test_close_non_owner_403(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, role_key: str
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup[role_key], f"{BRANCHES_URL}/{setup['main'].id}/close"
    )
    assert resp.status_code == 403, resp.content[:300]


# ---------------------------------------------------------------------------
# POST /api/v1/branches/{id}/reopen (Doc 04 §8.3)
# ---------------------------------------------------------------------------


def test_reopen_happy_200_and_audit(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['closed'].id}/reopen"
    )
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json()["deleted_at"] is None
    with tenant_context(tenant_a):
        assert Branch.objects.get(id=setup["closed"].id).deleted_at is None
        audit = AuditLog.objects.get(
            action="branch.reopened", entity_id=setup["closed"].id
        )
        assert audit.actor_id == setup["owner"].id
        assert audit.before_jsonb is not None
        assert audit.after_jsonb is not None
        assert audit.before_jsonb["deleted_at"] is not None
        assert audit.after_jsonb["deleted_at"] is None
    listed = Client().get(BRANCHES_URL, headers=auth_headers(setup["owner"]))
    assert "C01" in {b["code"] for b in listed.json()}


def test_reopen_idempotent_200(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Reopening a non-closed branch → 200 (idempotent, no audit row)."""
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{setup['main'].id}/reopen"
    )
    assert resp.status_code == 200, resp.content[:300]
    with tenant_context(tenant_a):
        assert (
            AuditLog.objects.filter(
                action="branch.reopened", entity_id=setup["main"].id
            ).count()
            == 0
        )


def test_reopen_missing_branch_404(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], f"{BRANCHES_URL}/{uuid.uuid4()}/reopen"
    )
    assert resp.status_code == 404, resp.content[:300]


@pytest.mark.parametrize(
    "role_key", ["manager", "receptionist", "technician", "pathologist"]
)
def test_reopen_non_owner_403(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any, role_key: str
) -> None:
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup[role_key], f"{BRANCHES_URL}/{setup['closed'].id}/reopen"
    )
    assert resp.status_code == 403, resp.content[:300]


# ---------------------------------------------------------------------------
# TN-23 (branch-ops facet): collection centre flags + result_entry gate intact
# ---------------------------------------------------------------------------


def test_tn23_collection_centre_created_with_flags(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-23 facet: a collection centre is creatable with its flags stored;
    result_entry_enabled defaults false (LAB-25 enforces the gate; the toggle
    itself is outside this ticket's five endpoints — see final report)."""
    setup = lab33_setup
    resp = _post_json(
        auth_headers,
        setup["owner"],
        BRANCHES_URL,
        {
            "code": "CC1",
            "name": "Collection Centre 1",
            "is_collection_centre": True,
        },
    )
    assert resp.status_code == 201, resp.content[:300]
    body = resp.json()
    assert body["is_collection_centre"] is True
    assert body["result_entry_enabled"] is False
    with tenant_context(tenant_a):
        centre = Branch.objects.get(code="CC1")
        assert centre.is_collection_centre is True
        assert centre.result_entry_enabled is False


def test_tn23_collection_centre_close_preconditions_apply(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """TN-23 facet: a collection centre closes under the same §8.3 rules."""
    setup = lab33_setup
    created = _post_json(
        auth_headers,
        setup["owner"],
        BRANCHES_URL,
        {"code": "CC2", "name": "CC Two", "is_collection_centre": True},
    )
    assert created.status_code == 201
    centre_id = created.json()["id"]
    with tenant_context(tenant_a):
        SampleFactory(
            branch_id=centre_id,
            status=Sample.Status.COLLECTED,
        )
    resp = _post_json(auth_headers, setup["owner"], f"{BRANCHES_URL}/{centre_id}/close")
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "branch_has_open_work"


# ---------------------------------------------------------------------------
# Cross-cutting: audit isolation between actions
# ---------------------------------------------------------------------------


def test_no_audit_row_on_failed_create(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """A rejected create (duplicate code) writes no audit row."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        before = AuditLog.objects.filter(action="branch.created").count()
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "M01", "name": "Dup"}
    )
    assert resp.status_code == 409
    with tenant_context(tenant_a):
        assert AuditLog.objects.filter(action="branch.created").count() == before


def test_patient_model_untouched_by_branch_patch(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Sanity: branch PATCH never touches patient rows (TN-18 guard)."""
    setup = lab33_setup
    with tenant_context(tenant_a):
        patient = PatientFactory(branch=setup["main"])
        patient_id = patient.id
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"name": "X"},
    )
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        assert Patient.objects.filter(id=patient_id).exists()


# ---------------------------------------------------------------------------
# Defensive-path coverage
# ---------------------------------------------------------------------------


def test_create_whitespace_name_422(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """A blank name passes the serializer but is rejected by the service."""
    setup = lab33_setup
    resp = _post_json(
        auth_headers, setup["owner"], BRANCHES_URL, {"code": "W01", "name": "   "}
    )
    assert resp.status_code == 422, resp.content[:300]


def test_create_duplicate_race_guard_409(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """The uq_branch_code race between exists() and INSERT maps to 409."""
    from unittest import mock

    from django.db import IntegrityError

    setup = lab33_setup
    with mock.patch.object(
        Branch.objects, "create", side_effect=IntegrityError("uq_branch_code")
    ):
        resp = _post_json(
            auth_headers, setup["owner"], BRANCHES_URL, {"code": "Q01", "name": "Race"}
        )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "duplicate_branch_code"


def test_create_uses_x_forwarded_for_ip_in_audit(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    headers = auth_headers(setup["owner"])
    headers["X-Forwarded-For"] = "203.0.113.9, 10.0.0.1"
    resp = Client().post(
        BRANCHES_URL,
        data=json.dumps({"code": "I01", "name": "IP Branch"}),
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 201, resp.content[:300]
    with tenant_context(tenant_a):
        audit = AuditLog.objects.get(
            action="branch.created", entity_id=resp.json()["id"]
        )
        assert audit.ip == "203.0.113.9"


def test_patch_blank_name_422(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    setup = lab33_setup
    resp = _patch_json(
        auth_headers,
        setup["owner"],
        f"{BRANCHES_URL}/{setup['main'].id}",
        {"name": "   "},
    )
    assert resp.status_code == 422, resp.content[:300]
    assert resp.json()["error"]["code"] == "validation_error"


def test_patch_code_claim_race_guard_409(
    tenant_a: Any, lab33_setup: Any, auth_headers: Any
) -> None:
    """Two concurrent PATCHes claiming the same new code: the INSERT-time
    uq_branch_code violation maps to 409, not 500."""
    from unittest import mock

    from django.db import IntegrityError

    setup = lab33_setup
    with mock.patch.object(
        Branch, "save", side_effect=IntegrityError("uq_branch_code")
    ):
        resp = _patch_json(
            auth_headers,
            setup["owner"],
            f"{BRANCHES_URL}/{setup['main'].id}",
            {"code": "N98"},
        )
    assert resp.status_code == 409, resp.content[:300]
    assert resp.json()["error"]["code"] == "duplicate_branch_code"
