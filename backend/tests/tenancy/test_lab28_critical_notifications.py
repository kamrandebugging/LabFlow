"""LAB-28 Test Suite: Critical notifications (Doc 03 §5.5 RS-10, §6.6, §8.5;
Doc 02 §5.6 v1.2; KAN-153; original LAB-33).

Covers (T-47):
- POST /api/v1/results/{id}/critical-notifications — roles M/P ONLY
  (exact §6.6 cell "M P"); 403 for O/R/T.
- ONLY on a result flagged critical -> 409 not_critical otherwise.
  404 out of scope / not found.
- Body: notified_name (required, non-empty, max 200), notified_at
  (required ISO 8601 datetime; future -> 422 notification_in_future),
  read_back (required boolean). Unknown fields rejected.
- -> 201 critical_notification row; caller stored as recorded_by.
  Audit result.critical_notified with event flag, same transaction.
- Append-only: multiple notifications allowed (each adds a row);
  no PUT/PATCH/DELETE route exists; DB-level REVOKE (P-5) covers mutation.
- Exceptions list clears: recording a notification removes the result from
  the "unnotified critical" set (derived state, §8.5/§11).
"""

import json
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.results.models import CriticalNotification, Result
from tests.factories.branch import BranchFactory
from tests.factories.results import CriticalNotificationFactory, ResultFactory
from tests.factories.samples import SampleFactory
from tests.factories.staff_user import StaffUserFactory

NOTIFY_URL = "/api/v1/results/{result_id}/critical-notifications"


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
def lab28_setup(tenant_a: Any) -> dict[str, Any]:
    """One critical result + one non-critical result, M/P/T/R/O users."""
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="path1@labflow.app"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="mgr1@labflow.app"
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="tech1@labflow.app"
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="recep1@labflow.app"
        )
        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="owner@labflow.app"
        )
        critical_result = ResultFactory(
            sample=SampleFactory(branch=branch),
            flag=Result.Flag.CRITICAL,
            status=Result.Status.APPROVED,
            value="450.0",
        )
        normal_result = ResultFactory(
            sample=SampleFactory(branch=branch),
            flag=Result.Flag.NORMAL,
            status=Result.Status.APPROVED,
            value="95.0",
        )
        return {
            "branch": branch,
            "pathologist": pathologist,
            "manager": manager,
            "technician": technician,
            "receptionist": receptionist,
            "owner": owner,
            "critical_result": critical_result,
            "normal_result": normal_result,
        }


def _post_notification(
    client: Client,
    headers: dict[str, str],
    result_id: Any,
    body: dict[str, Any] | None = None,
) -> Any:
    if body is None:
        body = {
            "notified_name": "Dr. Ahmed Raza",
            "notified_at": timezone.now().isoformat(),
            "read_back": True,
        }
    return client.post(
        NOTIFY_URL.format(result_id=result_id),
        data=json.dumps(body),
        content_type="application/json",
        headers=headers,
    )


class TestCriticalNotificationRecord:
    def test_pathologist_records_201(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["pathologist"])
        resp = _post_notification(client, headers, result.id)
        assert resp.status_code == 201, resp.content.decode()[:400]
        payload = resp.json()
        assert payload["result_id"] == str(result.id)
        assert payload["notified_name"] == "Dr. Ahmed Raza"
        assert payload["read_back"] is True
        assert payload["recorded_by"] == str(lab28_setup["pathologist"].id)
        with tenant_context(tenant_a):
            row = CriticalNotification.objects.get(pk=payload["id"])
            assert row.result_id == result.id
            assert row.recorded_by_id == lab28_setup["pathologist"].id
            assert row.read_back is True
            assert row.notified_at is not None
            # Audit: one immutable row, same transaction, event flag.
            audit = AuditLog.objects.get(
                action="result.critical_notified", entity_id=result.id
            )
            assert audit.actor_id == lab28_setup["pathologist"].id
            after = audit.after_jsonb or {}
            assert after["event"] == "result.critical_notified"
            assert after["notification_id"] == str(row.id)

    def test_manager_records_201(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["manager"])
        resp = _post_notification(client, headers, result.id)
        assert resp.status_code == 201, resp.content.decode()[:400]
        with tenant_context(tenant_a):
            assert CriticalNotification.objects.filter(
                result_id=result.id,
                recorded_by_id=lab28_setup["manager"].id,
            ).exists()

    @pytest.mark.parametrize("role_key", ["technician", "receptionist"])
    def test_other_roles_forbidden(
        self,
        client: Client,
        auth_headers: Any,
        lab28_setup: dict,
        tenant_a: Any,
        role_key: str,
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup[role_key])
        resp = _post_notification(client, headers, result.id)
        assert resp.status_code == 403, resp.content.decode()[:400]
        assert resp.json()["error"]["code"] == "forbidden"
        with tenant_context(tenant_a):
            assert CriticalNotification.objects.filter(result_id=result.id).count() == 0

    def test_non_critical_result_409(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["normal_result"]
            headers = auth_headers(lab28_setup["pathologist"])
        resp = _post_notification(client, headers, result.id)
        assert resp.status_code == 409, resp.content.decode()[:400]
        assert resp.json()["error"]["code"] == "not_critical"

    def test_unknown_result_404(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        import uuid

        with tenant_context(tenant_a):
            headers = auth_headers(lab28_setup["pathologist"])
        resp = _post_notification(client, headers, uuid.uuid4())
        assert resp.status_code == 404, resp.content.decode()[:400]

    def test_future_notified_at_422(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["pathologist"])
        body = {
            "notified_name": "Dr. Ahmed Raza",
            "notified_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            "read_back": True,
        }
        resp = _post_notification(client, headers, result.id, body=body)
        assert resp.status_code == 422, resp.content.decode()[:400]
        assert resp.json()["error"]["code"] == "notification_in_future"

    def test_missing_fields_422(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["pathologist"])
        resp = _post_notification(client, headers, result.id, body={})
        assert resp.status_code == 422, resp.content.decode()[:400]

    def test_empty_notified_name_422(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["pathologist"])
        body = {
            "notified_name": "   ",
            "notified_at": timezone.now().isoformat(),
            "read_back": False,
        }
        resp = _post_notification(client, headers, result.id, body=body)
        assert resp.status_code == 422, resp.content.decode()[:400]

    def test_unknown_fields_rejected(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["pathologist"])
        body = {
            "notified_name": "Dr. Ahmed Raza",
            "notified_at": timezone.now().isoformat(),
            "read_back": True,
            "hacker_field": "x",
        }
        resp = _post_notification(client, headers, result.id, body=body)
        assert resp.status_code == 422, resp.content.decode()[:400]

    def test_read_back_false_stored(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        """Read-back required for phone; electronic receipt may skip it."""
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["manager"])
        body = {
            "notified_name": "Duty Nurse Ward 3",
            "notified_at": timezone.now().isoformat(),
            "read_back": False,
        }
        resp = _post_notification(client, headers, result.id, body=body)
        assert resp.status_code == 201, resp.content.decode()[:400]
        with tenant_context(tenant_a):
            row = CriticalNotification.objects.get(pk=resp.json()["id"])
            assert row.read_back is False

    def test_append_only_second_notification_adds_row(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        """Append-only: a second notification ADDS a row, never edits."""
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
            headers = auth_headers(lab28_setup["pathologist"])
        r1 = _post_notification(client, headers, result.id)
        r2 = _post_notification(client, headers, result.id)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]
        with tenant_context(tenant_a):
            rows = list(
                CriticalNotification.objects.filter(result_id=result.id).order_by(
                    "created_at"
                )
            )
            assert len(rows) == 2
            # First row untouched by the second write.
            assert str(rows[0].id) == r1.json()["id"]

    def test_no_mutation_routes(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        """No PUT/PATCH/DELETE route exists for the notification resource."""
        with tenant_context(tenant_a):
            note = CriticalNotificationFactory()
            headers = auth_headers(lab28_setup["pathologist"])
            note_id = note.id
            result_id = note.result_id
        base = f"/api/v1/results/{result_id}/critical-notifications"
        for method in ("put", "patch", "delete"):
            resp = getattr(client, method)(
                base,
                data=json.dumps({}),
                content_type="application/json",
                headers=headers,
            )
            assert resp.status_code in (404, 405), (method, resp.status_code)
        # The row is still intact.
        with tenant_context(tenant_a):
            assert CriticalNotification.objects.filter(pk=note_id).exists()

    def test_exceptions_list_clears_on_record(
        self, client: Client, auth_headers: Any, lab28_setup: dict, tenant_a: Any
    ) -> None:
        """§8.5: once recorded, the result drops out of the unnotified-critical
        set — derived state, no extra write needed."""
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]

            def unnotified_critical() -> set:
                notified = set(
                    CriticalNotification.objects.filter(
                        result__flag=Result.Flag.CRITICAL
                    ).values_list("result_id", flat=True)
                )
                return set(
                    Result.objects.filter(flag=Result.Flag.CRITICAL)
                    .exclude(pk__in=notified)
                    .values_list("pk", flat=True)
                )

            assert result.pk in unnotified_critical()
            headers = auth_headers(lab28_setup["pathologist"])
        resp = _post_notification(client, headers, result.id)
        assert resp.status_code == 201
        with tenant_context(tenant_a):
            assert result.pk not in unnotified_critical()

    def test_unauthenticated_401(
        self, client: Client, lab28_setup: dict, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            result = lab28_setup["critical_result"]
        resp = _post_notification(
            client,
            {"Authorization": "Bearer invalid", "Host": "tenant-a.localhost"},
            result.id,
        )
        assert resp.status_code in (401, 403), resp.status_code
