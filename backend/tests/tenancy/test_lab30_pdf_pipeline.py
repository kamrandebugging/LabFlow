"""LAB-30 Test Suite: Asynchronous PDF pipeline (Doc 03 §5.6 RP-1/RP-2/RP-3,
§6.7, §10; KAN-155; original LAB-35 + LAB-43).

Covers:
- RP-1: report row created when sample first becomes ready (draft, v0);
  reports.generate_pdf enqueued (Celery, never synchronous).
- Task happy: version row + pdf_key=reports/{id}/{v}.pdf + status final +
  finalised_at; PDF bytes in storage (upload-then-insert).
- Idempotent: repeat run finds the version row -> exits success, no dup.
- T-34: forced render error -> no report_version row, report stays draft,
  generation_status=failed (visible); regenerate while running -> 409;
  manual retry after fix -> version 1.
- T-32: partial approval -> sample in_process, no report; last approval ->
  sample ready, report created, exactly one generate_pdf enqueued even if
  the approval is retried.
- POST /api/v1/reports/{id}/regenerate — roles O/M/P (-> 202); 409
  report_void; 409 generation_already_running; audit names generated_by.
- Amendment approved on final report -> new version, report -> amended.
- Audit event flag report.version_generated on completion.
"""

import json
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from django.test import Client, TestCase
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.reports.models import Report, ReportVersion
from apps.results.models import Result
from apps.samples.models import Sample
from tests.factories.branch import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.reports import ReportFactory
from tests.factories.results import ResultFactory
from tests.factories.samples import SampleFactory, SampleTestFactory
from tests.factories.staff_user import StaffUserFactory

APPROVE_URL = "/api/v1/results/{result_id}/approve"
REGENERATE_URL = "/api/v1/reports/{report_id}/regenerate"


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
def lab30_setup(tenant_a: Any) -> dict[str, Any]:
    """Two tests on one in_process sample, both results entered by technician."""
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="owner@labflow.app"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="mgr@labflow.app"
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="tech@labflow.app"
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="path1@labflow.app"
        )
        pathologist2 = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="path2@labflow.app"
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="recep@labflow.app"
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
            "owner": owner,
            "manager": manager,
            "technician": technician,
            "pathologist": pathologist,
            "pathologist2": pathologist2,
            "receptionist": receptionist,
            "test_a": test_a,
            "test_b": test_b,
            "sample": sample,
            "result_a": result_a,
            "result_b": result_b,
        }


def _approve(auth_headers: Any, user: Any, result_id: uuid.UUID, note: str = "") -> Any:
    body: dict[str, Any] = {"decision": "approved"}
    if note:
        body["note"] = note
    return Client().post(
        APPROVE_URL.format(result_id=result_id),
        data=json.dumps(body),
        content_type="application/json",
        headers=auth_headers(user),
    )


def _regenerate(auth_headers: Any, user: Any, report_id: uuid.UUID) -> Any:
    return Client().post(
        REGENERATE_URL.format(report_id=report_id),
        data=json.dumps({}),
        content_type="application/json",
        headers=auth_headers(user),
    )


def _schema(tenant_a: Any) -> str:
    return tenant_a.schema_name


# ---------------------------------------------------------------------------
# T-32: report created on ready, exactly one enqueue
# ---------------------------------------------------------------------------


def test_t32_partial_approval_no_report(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Partial approval leaves sample in_process and creates no report."""
    s = lab30_setup
    with TestCase.captureOnCommitCallbacks(execute=True):
        resp = _approve(auth_headers, s["pathologist"], s["result_a"].id)
    assert resp.status_code == 200
    with tenant_context(tenant_a):
        sample = Sample.objects.get(pk=s["sample"].id)
        assert sample.status == Sample.Status.IN_PROCESS
        assert not Report.objects.filter(sample=sample).exists()


def test_t32_last_approval_creates_report_and_enqueues_once(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Approving the last pending test -> sample ready, report created,
    exactly one generate_pdf enqueued even if the approval is retried."""
    s = lab30_setup
    with TestCase.captureOnCommitCallbacks(execute=True):
        assert (
            _approve(auth_headers, s["pathologist"], s["result_a"].id).status_code
            == 200
        )
        assert (
            _approve(auth_headers, s["pathologist2"], s["result_b"].id).status_code
            == 200
        )
        # Retry the approval -> 409, must not enqueue again.
        retry = _approve(auth_headers, s["pathologist2"], s["result_b"].id)
        assert retry.status_code == 409
    with tenant_context(tenant_a):
        sample = Sample.objects.get(pk=s["sample"].id)
        assert sample.status == Sample.Status.READY
        reports = list(Report.objects.filter(sample=sample))
        assert len(reports) == 1
        report = reports[0]
        # Eager Celery: the task already ran -> version 1 final.
        assert report.current_version == 1
        assert report.status == Report.Status.FINAL
        assert report.finalised_at is not None
        versions = list(ReportVersion.objects.filter(report=report))
        assert len(versions) == 1
        assert versions[0].pdf_key == f"reports/{report.id}/1.pdf"


# ---------------------------------------------------------------------------
# Task: happy path, idempotency, upload-then-insert
# ---------------------------------------------------------------------------


def test_task_happy_path(tenant_a: Any, lab30_setup: dict[str, Any]) -> None:
    """generate_pdf on a draft report -> version 1, final, PDF in storage."""
    from apps.reports.tasks import generate_pdf_task

    s = lab30_setup
    with tenant_context(tenant_a):
        sample = Sample.objects.get(pk=s["sample"].id)
        report = ReportFactory(sample=sample)
        result = generate_pdf_task(_schema(tenant_a), str(report.id), None, 1)
    assert result["status"] == "ok"
    assert result["version"] == 1
    with tenant_context(tenant_a):
        report.refresh_from_db()
        assert report.current_version == 1
        assert report.status == Report.Status.FINAL
        assert report.finalised_at is not None
        assert report.generation_status == Report.GenerationStatus.IDLE
        version = ReportVersion.objects.get(report=report, version=1)
        assert version.pdf_key == f"reports/{report.id}/1.pdf"
        # Upload-then-insert: the PDF bytes exist in storage.
        from apps.reports.storage import ReportStorage

        assert ReportStorage().pdf_exists(version.pdf_key)


def test_task_idempotent_rerun(tenant_a: Any, lab30_setup: dict[str, Any]) -> None:
    """A repeat run that finds the version row exits as success (no dup)."""
    from apps.reports.tasks import generate_pdf_task

    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"])
        first = generate_pdf_task(_schema(tenant_a), str(report.id), None, 1)
        second = generate_pdf_task(_schema(tenant_a), str(report.id), None, 1)
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second.get("deduplicated") is True
    with tenant_context(tenant_a):
        assert ReportVersion.objects.filter(report=report).count() == 1


def test_task_render_failure_leaves_no_version_row(
    tenant_a: Any, lab30_setup: dict[str, Any]
) -> None:
    """T-34: forced render error -> no report_version row, report stays
    draft, failure visible (generation_status=failed)."""
    from apps.reports.tasks import generate_pdf_task

    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"])
        with (
            patch(
                "apps.reports.tasks.render_report_pdf",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError),
        ):
            generate_pdf_task(_schema(tenant_a), str(report.id), None, 1)
    with tenant_context(tenant_a):
        report.refresh_from_db()
        assert ReportVersion.objects.filter(report=report).count() == 0
        assert report.status == Report.Status.DRAFT
        assert report.current_version == 0
        assert report.generation_status == Report.GenerationStatus.FAILED
        assert report.generation_error is not None


def test_task_upload_failure_leaves_no_version_row(
    tenant_a: Any, lab30_setup: dict[str, Any]
) -> None:
    """Upload-then-insert: storage failure -> no version row written."""
    from apps.reports.tasks import generate_pdf_task

    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"])
        with (
            patch(
                "apps.reports.storage.ReportStorage.save_pdf",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError),
        ):
            generate_pdf_task(_schema(tenant_a), str(report.id), None, 1)
    with tenant_context(tenant_a):
        report.refresh_from_db()
        assert ReportVersion.objects.filter(report=report).count() == 0
        assert report.generation_status == Report.GenerationStatus.FAILED


# ---------------------------------------------------------------------------
# Regenerate endpoint
# ---------------------------------------------------------------------------


def test_regenerate_happy_path(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """POST /reports/{id}/regenerate (O/M/P) -> 202, new version enqueued."""
    from apps.reports.tasks import generate_pdf_task

    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"])
        generate_pdf_task(_schema(tenant_a), str(report.id), None, 1)
        report.refresh_from_db()
        assert report.current_version == 1
    with TestCase.captureOnCommitCallbacks(execute=True):
        resp = _regenerate(auth_headers, s["manager"], report.id)
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"] == str(report.id)
    with tenant_context(tenant_a):
        report.refresh_from_db()
        # Eager: the new version already generated.
        assert report.current_version == 2
        assert report.status == Report.Status.AMENDED
        actions = list(
            AuditLog.objects.filter(entity_id=report.id).values_list(
                "action", flat=True
            )
        )
        assert "report.regenerate_requested" in actions
        regen = AuditLog.objects.get(
            entity_id=report.id, action="report.regenerate_requested"
        )
        assert regen.after_jsonb is not None
        assert regen.after_jsonb.get("generated_by") == str(s["manager"].id)


def test_regenerate_roles(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Only O/M/P may regenerate; T/R get 403."""
    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"])
    for user in (s["owner"], s["manager"], s["pathologist"]):
        with TestCase.captureOnCommitCallbacks(execute=True):
            resp = _regenerate(auth_headers, user, report.id)
        assert resp.status_code == 202, user.role
    for user in (s["technician"], s["receptionist"]):
        resp = _regenerate(auth_headers, user, report.id)
        assert resp.status_code == 403, user.role


def test_regenerate_void_report_409(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Regenerating a void report -> 409 report_void."""
    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"], status=Report.Status.VOID)
    resp = _regenerate(auth_headers, s["manager"], report.id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "report_void"


def test_regenerate_while_running_409(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """T-34: regenerate while one is running -> 409
    generation_already_running."""
    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(
            sample=s["sample"],
            generation_status=Report.GenerationStatus.RUNNING,
        )
    resp = _regenerate(auth_headers, s["manager"], report.id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "generation_already_running"


def test_regenerate_after_failure_works(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """T-34: manual retry after fixing data -> version 1 generated."""
    from apps.reports.tasks import generate_pdf_task

    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"])
        with (
            patch(
                "apps.reports.tasks.render_report_pdf",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError),
        ):
            generate_pdf_task(_schema(tenant_a), str(report.id), None, 1)
        report.refresh_from_db()
        assert report.generation_status == Report.GenerationStatus.FAILED
    # Manual retry via the endpoint (data now fine).
    with TestCase.captureOnCommitCallbacks(execute=True):
        resp = _regenerate(auth_headers, s["manager"], report.id)
    assert resp.status_code == 202
    with tenant_context(tenant_a):
        report.refresh_from_db()
        assert report.current_version == 1
        assert report.status == Report.Status.FINAL
        assert report.generation_status == Report.GenerationStatus.IDLE


def test_regenerate_unknown_report_404(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    s = lab30_setup
    resp = _regenerate(auth_headers, s["manager"], uuid.uuid4())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Amendment -> new version (RP-4)
# ---------------------------------------------------------------------------


def test_amendment_approval_enqueues_new_version(
    tenant_a: Any, lab30_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Approving an amendment on a final report -> new version generated,
    report status -> amended."""
    s = lab30_setup
    # Ready the sample first (report v1 generated eagerly).
    with TestCase.captureOnCommitCallbacks(execute=True):
        assert (
            _approve(auth_headers, s["pathologist"], s["result_a"].id).status_code
            == 200
        )
        assert (
            _approve(auth_headers, s["pathologist2"], s["result_b"].id).status_code
            == 200
        )
    with tenant_context(tenant_a):
        report = Report.objects.get(sample=s["sample"])
        assert report.current_version == 1
        assert report.status == Report.Status.FINAL
    # Amend result_a (approved) -> new entered row; approve it.
    client = Client()
    amend_resp = client.post(
        f"/api/v1/results/{s['result_a'].id}/amend",
        data=json.dumps({"value": "5.6", "unit": "mmol/L", "reason": "recalibrated"}),
        content_type="application/json",
        headers=auth_headers(s["technician"]),
    )
    assert amend_resp.status_code == 201, amend_resp.content[:300]
    new_result_id = amend_resp.json()["id"]
    with TestCase.captureOnCommitCallbacks(execute=True):
        approve_resp = client.post(
            APPROVE_URL.format(result_id=new_result_id),
            data=json.dumps({"decision": "approved", "note": "verified"}),
            content_type="application/json",
            headers=auth_headers(s["pathologist2"]),
        )
    assert approve_resp.status_code == 200, approve_resp.content[:300]
    with tenant_context(tenant_a):
        report.refresh_from_db()
        assert report.current_version == 2
        assert report.status == Report.Status.AMENDED
        assert ReportVersion.objects.filter(report=report).count() == 2


# ---------------------------------------------------------------------------
# Audit: event flag + generated_by
# ---------------------------------------------------------------------------


def test_version_generated_event_flag(
    tenant_a: Any, lab30_setup: dict[str, Any]
) -> None:
    """Completion writes audit report.version_generated with the event flag."""
    from apps.reports.tasks import generate_pdf_task

    s = lab30_setup
    with tenant_context(tenant_a):
        report = ReportFactory(sample=s["sample"])
        generate_pdf_task(_schema(tenant_a), str(report.id), str(s["manager"].id), 1)
        rows = list(
            AuditLog.objects.filter(
                entity_id=report.id, action="report.version_generated"
            )
        )
        assert len(rows) == 1
        assert rows[0].after_jsonb is not None
        assert rows[0].after_jsonb.get("event") == "report.version_generated"
        assert rows[0].after_jsonb.get("version") == 1
