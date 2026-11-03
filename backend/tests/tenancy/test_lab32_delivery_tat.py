"""LAB-32 Test Suite: Report delivery dispatch + TAT metrics
(Doc 03 §5.6 RP-6/RP-7, §6.7, §10, §11.2; KAN-157; original LAB-37 + LAB-41).
Backend only.

Part 1 — Delivery dispatch:
- T-35: no consent -> 422 no_consent; billing hold + unpaid invoice -> 409
  billing_hold; FAILED delivery retried by the beat sweep only after
  next_attempt_at.
- POST /api/v1/reports/{id}/deliver — roles O M R; strict serializer;
  guards in order: 404 unknown report; 409 report_void; 409 report_not_final
  (RP-V2); 422 no_consent (PT-7); 409 billing_hold (RP-7); 404 unknown /
  foreign contact; 422 channel/contact kind mismatch.
- Happy: -> 202 with the delivery row, PENDING, access token minted,
  reports.deliver enqueued via on_commit, audit report.delivery_created.
- Idempotency: second deliver for the same channel + contact within 10 min
  -> 200 with the existing PENDING delivery (no duplicate row, no new
  token, no second enqueue).
- Task reports.deliver: happy -> SENT + sent_at, whatsapp_url hand-off for
  whatsapp (None for email), message rendered from the report_ready
  notification template in the tenant default language (fallback when the
  template is not seeded); a re-run on a SENT row never re-sends; failure
  -> FAILED + attempts+1 + next_attempt_at backoff; attempts cap parks the
  row for manual handling. Audit report.delivery_sent with the event flag.
- Beat sweep reports.retry_failed_deliveries (every 15 min): re-enqueues
  FAILED rows with next_attempt_at <= now and attempts < 5 only; claims
  each row with a lease so two beat runs cannot double-enqueue.

Part 2 — TAT metrics (Doc 03 §11.2):
- Pure functions in apps/reports/metrics.py over plain data (no DB).
- Definition string printed with every figure; stage split from
  sample_event timestamps; median + p90 math; rejected/cancelled excluded
  and counted separately; per-branch-per-week grouping.
- Service compute_tat_metrics(branch_id, week): aggregates + definition.
  No API endpoint in this ticket (observability endpoints are a later LAB).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any, cast
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test import Client, TestCase
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser, TenantSetting
from apps.billing.models import Invoice
from apps.notifications.models import NotificationTemplate
from apps.patients.models import PatientConsent, PatientContact
from apps.reports.models import Report, ReportAccessToken, ReportDelivery
from apps.samples.models import Sample
from tests.factories.billing import InvoiceFactory
from tests.factories.branch import BranchFactory
from tests.factories.notifications import NotificationTemplateFactory
from tests.factories.patients import (
    PatientConsentFactory,
    PatientContactFactory,
    PatientFactory,
)
from tests.factories.reports import ReportDeliveryFactory, ReportFactory
from tests.factories.samples import SampleFactory
from tests.factories.staff_user import StaffUserFactory

KARACHI = ZoneInfo("Asia/Karachi")
DELIVER_URL = "/api/v1/reports/{report_id}/deliver"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser | None = None, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        headers = {"Host": f"{slug}.localhost"}
        if staff_user is not None:
            session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
            headers["Authorization"] = f"Bearer {session['access']}"
        return headers

    return _make_headers


@pytest.fixture
def lab32_setup(tenant_a: Any) -> dict[str, Any]:
    """Branch + 5 roles + patient with whatsapp/email contacts and consents +
    a PAID invoice + collected sample + FINAL report v1."""
    with tenant_context(tenant_a):
        branch = BranchFactory(
            code="MN2", name="Main Laboratory", phone="+92 42 3577 1234"
        )
        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="owner32@labflow.app"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="mgr32@labflow.app"
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="recep32@labflow.app"
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="tech32@labflow.app"
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="path32@labflow.app"
        )
        patient = PatientFactory(branch=branch, name="TAT Patient")
        wa_contact = PatientContactFactory(
            patient=patient,
            kind=PatientContact.Kind.WHATSAPP,
            value="03219876543",
            is_primary=True,
        )
        email_contact = PatientContactFactory(
            patient=patient,
            kind=PatientContact.Kind.EMAIL,
            value="patient32@example.com",
            is_primary=False,
        )
        PatientConsentFactory(
            patient=patient,
            channel=PatientConsent.Channel.WHATSAPP,
            granted_by=receptionist,
        )
        PatientConsentFactory(
            patient=patient,
            channel=PatientConsent.Channel.EMAIL,
            granted_by=receptionist,
        )
        invoice = InvoiceFactory(
            patient=patient, branch=branch, status=Invoice.Status.PAID
        )
        sample = SampleFactory(
            invoice=invoice,
            branch=branch,
            collected_by=receptionist,
            status=Sample.Status.COLLECTED,
        )
        report = ReportFactory(
            sample=sample,
            status=Report.Status.FINAL,
            current_version=1,
            finalised_at=timezone.now(),
        )
        return {
            "tenant": tenant_a,
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "pathologist": pathologist,
            "patient": patient,
            "wa_contact": wa_contact,
            "email_contact": email_contact,
            "invoice": invoice,
            "sample": sample,
            "report": report,
        }


def _schema(tenant_a: Any) -> str:
    return tenant_a.schema_name


def _post_deliver(
    client: Client,
    headers: dict[str, str],
    report_id: Any,
    body: dict[str, Any],
) -> Any:
    kwargs: dict[str, Any] = {
        "HTTP_HOST": headers["Host"],
        "data": json.dumps(body),
        "content_type": "application/json",
    }
    if "Authorization" in headers:
        kwargs["HTTP_AUTHORIZATION"] = headers["Authorization"]
    return client.post(DELIVER_URL.format(report_id=report_id), **kwargs)


def _after(audit: AuditLog) -> dict[str, Any]:
    assert isinstance(audit.after_jsonb, dict)
    return cast(dict[str, Any], audit.after_jsonb)


# ---------------------------------------------------------------------------
# POST /api/v1/reports/{id}/deliver — happy path + roles + serializer
# ---------------------------------------------------------------------------


class TestDeliverEndpoint:
    def test_deliver_happy_path_whatsapp(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """O/M/R -> 202; PENDING row; token minted; task enqueued; audit."""
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        headers = auth_headers(s["receptionist"])
        with tenant_context(s["tenant"]):
            report_id = s["report"].id
            contact_id = s["wa_contact"].id
        with (
            patch.object(deliver_report_task, "delay") as mock_delay,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            resp = _post_deliver(
                client,
                headers,
                report_id,
                {"channel": "whatsapp", "contact_id": str(contact_id)},
            )
        assert resp.status_code == 202, resp.content.decode()[:600]
        body = resp.json()
        assert body["channel"] == "whatsapp"
        assert body["contact_id"] == str(contact_id)
        assert body["status"] == "PENDING"
        assert body["report_id"] == str(report_id)
        # staff fallback link: the call-time token's plain link, returned once
        assert body["link"].startswith("/api/v1/report-access/")
        assert "token_id" in body

        mock_delay.assert_called_once()
        enq_args = mock_delay.call_args.args
        assert enq_args[0] == _schema(s["tenant"])
        delivery_pk = enq_args[1]

        with tenant_context(s["tenant"]):
            delivery = ReportDelivery.objects.get(pk=delivery_pk)
            assert delivery.report_id == report_id
            assert delivery.channel == "whatsapp"
            assert delivery.contact_id == contact_id
            assert delivery.status == ReportDelivery.Status.PENDING
            assert delivery.attempts == 0
            # token minted at call time; only the hash stored
            token = ReportAccessToken.objects.get(pk=body["token_id"])
            assert token.report_id == report_id
            assert token.token_hash.startswith("$argon2")
            # audit: delivery create, no plain token anywhere
            audit = AuditLog.objects.get(action="report.delivery_created")
            assert audit.entity_type == "report_delivery"
            assert audit.entity_id == delivery.id
            assert _after(audit)["delivery_id"] == str(delivery.id)
            assert _after(audit)["token_id"] == str(token.id)
            assert "/api/v1/report-access/" not in str(audit.after_jsonb)

    def test_deliver_roles_omr_only(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        s = lab32_setup
        with tenant_context(s["tenant"]):
            report_id = s["report"].id
            patient = s["patient"]
        for i, (user, ok) in enumerate(
            (
                (s["owner"], True),
                (s["manager"], True),
                (s["receptionist"], True),
                (s["technician"], False),
                (s["pathologist"], False),
            )
        ):
            # fresh contact per role so the 10-minute idempotency dedupe
            # cannot turn an allowed 202 into a 200
            with tenant_context(s["tenant"]):
                contact = PatientContactFactory(
                    patient=patient,
                    kind=PatientContact.Kind.WHATSAPP,
                    value=f"0300555{i:04d}",
                )
            resp = _post_deliver(
                client,
                auth_headers(user),
                report_id,
                {"channel": "whatsapp", "contact_id": str(contact.id)},
            )
            assert resp.status_code == (202 if ok else 403), (
                user.role,
                resp.content.decode()[:300],
            )
            if not ok:
                assert resp.json()["error"]["code"] == "forbidden"

    def test_deliver_strict_serializer_rejects_unknown_fields(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            report_id = s["report"].id
            contact_id = s["wa_contact"].id
        resp = _post_deliver(
            client,
            headers,
            report_id,
            {
                "channel": "whatsapp",
                "contact_id": str(contact_id),
                "priority": "urgent",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_deliver_missing_fields_422(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            report_id = s["report"].id
        resp = _post_deliver(client, headers, report_id, {"channel": "whatsapp"})
        assert resp.status_code == 422

    def test_deliver_unknown_report_404(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            contact_id = s["wa_contact"].id
        resp = _post_deliver(
            client,
            headers,
            uuid.uuid4(),
            {"channel": "whatsapp", "contact_id": str(contact_id)},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_deliver_void_report_409(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            report = s["report"]
            report.status = Report.Status.VOID
            report.save(update_fields=["status", "updated_at"])
            report_id, contact_id = report.id, s["wa_contact"].id
        resp = _post_deliver(
            client,
            headers,
            report_id,
            {"channel": "whatsapp", "contact_id": str(contact_id)},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "report_void"

    def test_deliver_not_final_409(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """RP-V2: draft report -> 409 report_not_final."""
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            report = ReportFactory(
                sample=s["sample"],
                status=Report.Status.DRAFT,
                current_version=0,
            )
            contact_id = s["wa_contact"].id
        resp = _post_deliver(
            client,
            headers,
            report.id,
            {"channel": "whatsapp", "contact_id": str(contact_id)},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "report_not_final"

    def test_deliver_no_consent_422(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """T-35a / PT-7: no consent row for the channel -> 422 no_consent."""
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            # revoke the whatsapp consent -> consent no longer counts
            PatientConsent.objects.filter(
                patient=s["patient"],
                channel=PatientConsent.Channel.WHATSAPP,
            ).update(revoked_at=timezone.now())
            report_id, contact_id = s["report"].id, s["wa_contact"].id
        resp = _post_deliver(
            client,
            headers,
            report_id,
            {"channel": "whatsapp", "contact_id": str(contact_id)},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "no_consent"

    def test_deliver_billing_hold_unpaid_409(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """T-35b / RP-7: hold on + invoice unpaid -> 409 billing_hold."""
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            TenantSetting.objects.update_or_create(
                key="billing_hold_enabled",
                defaults={"value": "true", "updated_by": None},
            )
            invoice = s["invoice"]
            invoice.status = "unpaid"
            invoice.save(update_fields=["status", "updated_at"])
            report_id, contact_id = s["report"].id, s["wa_contact"].id
        resp = _post_deliver(
            client,
            headers,
            report_id,
            {"channel": "whatsapp", "contact_id": str(contact_id)},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "billing_hold"

    def test_deliver_billing_hold_paid_passes(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """RP-7: hold on + invoice fully paid -> 202."""
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            TenantSetting.objects.update_or_create(
                key="billing_hold_enabled",
                defaults={"value": "true", "updated_by": None},
            )
            report_id, contact_id = s["report"].id, s["wa_contact"].id
        with (
            patch.object(deliver_report_task, "delay"),
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            resp = _post_deliver(
                client,
                headers,
                report_id,
                {"channel": "whatsapp", "contact_id": str(contact_id)},
            )
        assert resp.status_code == 202, resp.content.decode()[:600]

    def test_deliver_unknown_contact_404(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            report_id = s["report"].id
        resp = _post_deliver(
            client,
            headers,
            report_id,
            {"channel": "whatsapp", "contact_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "contact_not_found"

    def test_deliver_foreign_patient_contact_404(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """A contact of another patient -> 404 (tenant-scoped, no leak)."""
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            other = PatientContactFactory(
                kind=PatientContact.Kind.WHATSAPP, value="03009998888"
            )
            report_id = s["report"].id
        resp = _post_deliver(
            client,
            headers,
            report_id,
            {"channel": "whatsapp", "contact_id": str(other.id)},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "contact_not_found"

    def test_deliver_channel_contact_kind_mismatch_422(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """channel=email with a whatsapp contact -> 422."""
        s = lab32_setup
        headers = auth_headers(s["manager"])
        with tenant_context(s["tenant"]):
            report_id, contact_id = s["report"].id, s["wa_contact"].id
        resp = _post_deliver(
            client,
            headers,
            report_id,
            {"channel": "email", "contact_id": str(contact_id)},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "contact_channel_mismatch"

    def test_deliver_idempotent_within_10_minutes(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """Second deliver for same channel+contact within 10 min -> 200 with
        the existing PENDING delivery; no duplicate row, token or enqueue."""
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        headers = auth_headers(s["receptionist"])
        with tenant_context(s["tenant"]):
            report_id, contact_id = s["report"].id, s["wa_contact"].id
            tokens_before = ReportAccessToken.objects.count()
        body = {"channel": "whatsapp", "contact_id": str(contact_id)}
        with (
            patch.object(deliver_report_task, "delay") as mock_delay,
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            first = _post_deliver(client, headers, report_id, body)
            assert first.status_code == 202, first.content.decode()[:400]
            second = _post_deliver(client, headers, report_id, body)
        assert second.status_code == 200, second.content.decode()[:400]
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["status"] == "PENDING"
        # dedupe response carries no new token
        assert "token_id" not in second.json()
        mock_delay.assert_called_once()
        with tenant_context(s["tenant"]):
            assert (
                ReportDelivery.objects.filter(
                    report_id=report_id,
                    channel="whatsapp",
                    contact_id=contact_id,
                ).count()
                == 1
            )
            assert ReportAccessToken.objects.count() == tokens_before + 1

    def test_deliver_different_contact_is_new_delivery(
        self, client: Client, auth_headers: Any, lab32_setup: dict[str, Any]
    ) -> None:
        """Same channel, different contact -> a second delivery row (202)."""
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        headers = auth_headers(s["receptionist"])
        with tenant_context(s["tenant"]):
            patient = s["patient"]
            second_wa = PatientContactFactory(
                patient=patient,
                kind=PatientContact.Kind.WHATSAPP,
                value="03001112222",
            )
            report_id = s["report"].id
            first_contact = s["wa_contact"].id
        with (
            patch.object(deliver_report_task, "delay"),
            TestCase.captureOnCommitCallbacks(execute=True),
        ):
            r1 = _post_deliver(
                client,
                headers,
                report_id,
                {"channel": "whatsapp", "contact_id": str(first_contact)},
            )
            r2 = _post_deliver(
                client,
                headers,
                report_id,
                {"channel": "whatsapp", "contact_id": str(second_wa.id)},
            )
        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["id"] != r2.json()["id"]


# ---------------------------------------------------------------------------
# Celery task reports.deliver
# ---------------------------------------------------------------------------


def _make_template(tenant: Any, channel: str, locale: str = "en") -> Any:
    with tenant_context(tenant):
        return NotificationTemplateFactory(
            key="report_ready",
            locale=locale,
            channel=channel,
            subject="Your report is ready",
            body=(
                "Dear {{ patient_name }}, your report ({{ accession_id }}) "
                "is ready: {{ patient_link }}"
            ),
            template_context_schema={
                "variables": [
                    "patient_name",
                    "accession_id",
                    "patient_link",
                    "lab_name",
                ]
            },
        )


class TestDeliverTask:
    def test_task_happy_path_whatsapp(self, lab32_setup: dict[str, Any]) -> None:
        """PENDING delivery -> SENT + sent_at; whatsapp_url click-to-send
        hand-off stored; token re-minted at send time; audit + event flag."""
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        _make_template(s["tenant"], "whatsapp")
        with tenant_context(s["tenant"]):
            delivery = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.WHATSAPP,
                contact=s["wa_contact"],
                status=ReportDelivery.Status.PENDING,
            )
            tokens_before = ReportAccessToken.objects.count()
            result = deliver_report_task(_schema(s["tenant"]), str(delivery.id))
        assert result["status"] == "ok"
        with tenant_context(s["tenant"]):
            delivery.refresh_from_db()
            assert delivery.status == ReportDelivery.Status.SENT
            assert delivery.sent_at is not None
            assert delivery.attempts == 0
            assert delivery.whatsapp_url is not None
            assert delivery.whatsapp_url.startswith("https://wa.me/03219876543?text=")
            assert "report-access" in delivery.whatsapp_url
            # plain token never stored; a fresh token row exists for the send
            assert ReportAccessToken.objects.count() == tokens_before + 1
            audit = AuditLog.objects.get(action="report.delivery_sent")
            assert audit.entity_type == "report_delivery"
            assert audit.entity_id == delivery.id
            assert _after(audit)["event"] == "report.delivery_sent"
            assert _after(audit)["channel"] == "whatsapp"

    def test_task_happy_path_email_no_whatsapp_url(
        self, lab32_setup: dict[str, Any]
    ) -> None:
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        _make_template(s["tenant"], "email")
        with tenant_context(s["tenant"]):
            delivery = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.EMAIL,
                contact=s["email_contact"],
                status=ReportDelivery.Status.PENDING,
            )
            result = deliver_report_task(_schema(s["tenant"]), str(delivery.id))
        assert result["status"] == "ok"
        with tenant_context(s["tenant"]):
            delivery.refresh_from_db()
            assert delivery.status == ReportDelivery.Status.SENT
            assert delivery.whatsapp_url is None

    def test_task_fallback_message_without_template(
        self, lab32_setup: dict[str, Any]
    ) -> None:
        """No report_ready template seeded -> interim fallback still sends."""
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        with tenant_context(s["tenant"]):
            assert NotificationTemplate.objects.filter(key="report_ready").count() == 0
            delivery = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.WHATSAPP,
                contact=s["wa_contact"],
                status=ReportDelivery.Status.PENDING,
            )
            result = deliver_report_task(_schema(s["tenant"]), str(delivery.id))
        assert result["status"] == "ok"
        assert result["template"] == "fallback"
        with tenant_context(s["tenant"]):
            delivery.refresh_from_db()
            assert delivery.status == ReportDelivery.Status.SENT

    def test_task_never_resends_sent_row(self, lab32_setup: dict[str, Any]) -> None:
        """Re-running on a SENT row is a no-op: no new token, no new audit."""
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        _make_template(s["tenant"], "whatsapp")
        with tenant_context(s["tenant"]):
            delivery = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.WHATSAPP,
                contact=s["wa_contact"],
                status=ReportDelivery.Status.PENDING,
            )
            first = deliver_report_task(_schema(s["tenant"]), str(delivery.id))
            tokens_after_first = ReportAccessToken.objects.count()
            audits_after_first = AuditLog.objects.filter(
                action="report.delivery_sent"
            ).count()
            second = deliver_report_task(_schema(s["tenant"]), str(delivery.id))
        assert first["status"] == "ok"
        assert second["status"] == "skipped"
        assert second["reason"] == "already_sent"
        with tenant_context(s["tenant"]):
            assert ReportAccessToken.objects.count() == tokens_after_first
            assert (
                AuditLog.objects.filter(action="report.delivery_sent").count()
                == audits_after_first
            )

    def test_task_unknown_delivery_skipped(self, lab32_setup: dict[str, Any]) -> None:
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        with tenant_context(s["tenant"]):
            result = deliver_report_task(_schema(s["tenant"]), str(uuid.uuid4()))
        assert result["status"] == "skipped"
        assert result["reason"] == "delivery_not_found"

    def test_task_failure_records_failed_with_backoff(
        self, lab32_setup: dict[str, Any]
    ) -> None:
        """Provider/build failure -> FAILED, attempts+1, next_attempt_at set,
        last_error recorded; audit report.delivery_failed."""
        from apps.reports import tasks as tasks_module
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        _make_template(s["tenant"], "whatsapp")
        with tenant_context(s["tenant"]):
            delivery = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.WHATSAPP,
                contact=s["wa_contact"],
                status=ReportDelivery.Status.PENDING,
            )
            before = timezone.now()
            with patch.object(
                tasks_module,
                "_build_delivery_message",
                side_effect=RuntimeError("provider down"),
            ):
                result = deliver_report_task(_schema(s["tenant"]), str(delivery.id))
        assert result["status"] == "failed"
        with tenant_context(s["tenant"]):
            delivery.refresh_from_db()
            assert delivery.status == ReportDelivery.Status.FAILED
            assert delivery.attempts == 1
            assert delivery.next_attempt_at is not None
            assert delivery.next_attempt_at > before
            assert "RuntimeError" in (delivery.last_error or "")
            assert delivery.sent_at is None
            audit = AuditLog.objects.get(action="report.delivery_failed")
            assert _after(audit)["event"] == "report.delivery_failed"

    def test_task_attempts_cap_parks_row(self, lab32_setup: dict[str, Any]) -> None:
        """attempts already at the cap -> parked: next_attempt_at None,
        left FAILED for manual handling, never re-sent."""
        from apps.reports import tasks as tasks_module
        from apps.reports.tasks import deliver_report_task

        s = lab32_setup
        _make_template(s["tenant"], "whatsapp")
        with tenant_context(s["tenant"]):
            delivery = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.WHATSAPP,
                contact=s["wa_contact"],
                status=ReportDelivery.Status.FAILED,
                attempts=5,
                next_attempt_at=timezone.now() - timedelta(minutes=1),
            )
            with patch.object(
                tasks_module,
                "_build_delivery_message",
                side_effect=RuntimeError("provider down"),
            ):
                result = deliver_report_task(_schema(s["tenant"]), str(delivery.id))
        assert result["status"] == "skipped"
        assert result["reason"] == "attempts_exhausted"
        with tenant_context(s["tenant"]):
            delivery.refresh_from_db()
            assert delivery.status == ReportDelivery.Status.FAILED
            assert delivery.next_attempt_at is None


# ---------------------------------------------------------------------------
# Beat sweep reports.retry_failed_deliveries
# ---------------------------------------------------------------------------


class TestRetrySweep:
    def _seed_rows(self, s: dict[str, Any]) -> dict[str, Any]:
        now = timezone.now()
        with tenant_context(s["tenant"]):
            due = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.WHATSAPP,
                contact=s["wa_contact"],
                status=ReportDelivery.Status.FAILED,
                attempts=1,
                next_attempt_at=now - timedelta(minutes=1),
            )
            future = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.WHATSAPP,
                contact=s["wa_contact"],
                status=ReportDelivery.Status.FAILED,
                attempts=1,
                next_attempt_at=now + timedelta(hours=2),
            )
            capped = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.EMAIL,
                contact=s["email_contact"],
                status=ReportDelivery.Status.FAILED,
                attempts=5,
                next_attempt_at=now - timedelta(minutes=1),
            )
            pending = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.EMAIL,
                contact=s["email_contact"],
                status=ReportDelivery.Status.PENDING,
            )
            sent = ReportDeliveryFactory(
                report=s["report"],
                channel=ReportDelivery.Channel.EMAIL,
                contact=s["email_contact"],
                status=ReportDelivery.Status.SENT,
            )
            return {
                "due": due,
                "future": future,
                "capped": capped,
                "pending": pending,
                "sent": sent,
            }

    def test_sweep_reenqueues_only_due_failed(
        self, lab32_setup: dict[str, Any]
    ) -> None:
        """T-35c: only the due FAILED row is re-enqueued; the claim lease is
        set so a concurrent beat run cannot pick it up again."""
        from apps.reports.tasks import deliver_report_task, retry_failed_deliveries_task

        s = lab32_setup
        rows = self._seed_rows(s)
        with patch.object(deliver_report_task, "delay") as mock_delay:
            result = retry_failed_deliveries_task()
        mock_delay.assert_called_once()
        args = mock_delay.call_args.args
        assert args[0] == _schema(s["tenant"])
        assert args[1] == str(rows["due"].id)
        assert result["requeued"] == 1
        with tenant_context(s["tenant"]):
            rows["due"].refresh_from_db()
            # claim lease: pushed into the future
            assert rows["due"].next_attempt_at is not None
            assert rows["due"].next_attempt_at > timezone.now()
            for key in ("future", "capped", "pending", "sent"):
                rows[key].refresh_from_db()
            assert rows["future"].status == ReportDelivery.Status.FAILED
            assert rows["capped"].status == ReportDelivery.Status.FAILED
            assert rows["capped"].next_attempt_at is not None  # untouched
            assert rows["pending"].status == ReportDelivery.Status.PENDING
            assert rows["sent"].status == ReportDelivery.Status.SENT

    def test_sweep_registered_every_15_minutes(self) -> None:
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE.get(
            "reports-retry-failed-deliveries-15min"
        )
        assert entry is not None
        assert entry["task"] == "reports.retry_failed_deliveries"
        assert entry["schedule"] == 900.0


# ---------------------------------------------------------------------------
# Part 2 — TAT metrics (pure functions + service)
# ---------------------------------------------------------------------------


class TestTatDefinition:
    def test_definition_string_present(self) -> None:
        from apps.reports.metrics import TAT_DEFINITION

        assert "report.finalised_at" in TAT_DEFINITION
        assert "sample.collected_at" in TAT_DEFINITION
        assert "final report" in TAT_DEFINITION

    def test_stage_split_from_events(self) -> None:
        from apps.reports.metrics import stage_durations_seconds

        base = datetime(2026, 10, 5, 8, 0, tzinfo=KARACHI)
        events = [
            ("COLLECTED", base),
            ("RECEIVED", base + timedelta(minutes=10)),
            ("IN_PROCESS", base + timedelta(minutes=30)),
            ("READY", base + timedelta(minutes=60)),
        ]
        finalised = base + timedelta(minutes=90)
        stages = stage_durations_seconds(base, events, finalised)
        assert stages["collection_to_receipt"] == pytest.approx(600.0)
        assert stages["receipt_to_in_process"] == pytest.approx(1200.0)
        assert stages["in_process_to_ready"] == pytest.approx(1800.0)
        assert stages["ready_to_finalised"] == pytest.approx(1800.0)

    def test_missing_stage_is_none(self) -> None:
        """A sample that skipped RECEIVED still yields the other stages."""
        from apps.reports.metrics import stage_durations_seconds

        base = datetime(2026, 10, 5, 8, 0, tzinfo=KARACHI)
        events = [
            ("COLLECTED", base),
            ("IN_PROCESS", base + timedelta(minutes=30)),
            ("READY", base + timedelta(minutes=60)),
        ]
        finalised = base + timedelta(minutes=90)
        stages = stage_durations_seconds(base, events, finalised)
        assert stages["collection_to_receipt"] is None
        assert stages["receipt_to_in_process"] is None
        assert stages["in_process_to_ready"] == pytest.approx(1800.0)
        assert stages["ready_to_finalised"] == pytest.approx(1800.0)

    def test_median_and_p90_math(self) -> None:
        from apps.reports.metrics import median_seconds, percentile_seconds

        values = [10.0, 20.0, 30.0, 40.0]
        assert median_seconds(values) == pytest.approx(25.0)
        # linear interpolation: rank 0.9*(4-1)=2.7 -> 30 + 0.7*10
        assert percentile_seconds(values, 90) == pytest.approx(37.0)
        assert median_seconds([]) is None
        assert percentile_seconds([], 90) is None
        assert median_seconds([5.0]) == pytest.approx(5.0)

    def test_aggregate_excludes_rejected_cancelled_and_counts_them(self) -> None:
        from apps.reports.metrics import aggregate_tat

        base = datetime(2026, 10, 5, 8, 0, tzinfo=KARACHI)
        rows = [
            {
                "branch_id": "b1",
                "week": (2026, 41),
                "collected_at": base,
                "finalised_at": base + timedelta(hours=2),
                "events": [],
                "status": "ready",
            },
            {
                "branch_id": "b1",
                "week": (2026, 41),
                "collected_at": base,
                "finalised_at": base + timedelta(hours=4),
                "events": [],
                "status": "ready",
            },
            {
                "branch_id": "b1",
                "week": (2026, 41),
                "collected_at": base,
                "finalised_at": None,
                "events": [],
                "status": "rejected",
            },
            {
                "branch_id": "b1",
                "week": (2026, 41),
                "collected_at": base,
                "finalised_at": None,
                "events": [],
                "status": "cancelled",
            },
        ]
        out = aggregate_tat(rows)
        assert "report.finalised_at" in out["definition"]
        group = out["per_branch_week"]["b1"][(2026, 41)]
        assert group["count"] == 2
        assert group["tat_median_seconds"] == pytest.approx(10800.0)
        assert out["excluded"]["rejected"] == 1
        assert out["excluded"]["cancelled"] == 1

    def test_aggregate_groups_per_branch_per_week(self) -> None:
        from apps.reports.metrics import aggregate_tat

        base = datetime(2026, 10, 5, 8, 0, tzinfo=KARACHI)  # ISO week 41
        other_week = datetime(2026, 10, 12, 8, 0, tzinfo=KARACHI)  # ISO week 42

        def row(branch: str, collected: datetime, hours: float) -> dict[str, Any]:
            return {
                "branch_id": branch,
                "week": collected.isocalendar()[:2],
                "collected_at": collected,
                "finalised_at": collected + timedelta(hours=hours),
                "events": [],
                "status": "ready",
            }

        out = aggregate_tat(
            [
                row("b1", base, 2),
                row("b1", base, 4),
                row("b2", base, 6),
                row("b1", other_week, 8),
            ]
        )
        groups = out["per_branch_week"]
        assert set(groups) == {"b1", "b2"}
        assert set(groups["b1"]) == {(2026, 41), (2026, 42)}
        assert groups["b1"][(2026, 41)]["count"] == 2
        assert groups["b2"][(2026, 41)]["count"] == 1
        assert groups["b1"][(2026, 42)]["tat_median_seconds"] == pytest.approx(28800.0)

    def test_aggregate_stage_medians(self) -> None:
        from apps.reports.metrics import aggregate_tat

        base = datetime(2026, 10, 5, 8, 0, tzinfo=KARACHI)
        rows = []
        for i, ready_min in enumerate((60, 120)):
            collected = base + timedelta(minutes=i)
            rows.append(
                {
                    "branch_id": "b1",
                    "week": (2026, 41),
                    "collected_at": collected,
                    "finalised_at": collected + timedelta(minutes=ready_min + 30),
                    "events": [
                        ("COLLECTED", collected),
                        ("RECEIVED", collected + timedelta(minutes=10)),
                        ("IN_PROCESS", collected + timedelta(minutes=20)),
                        ("READY", collected + timedelta(minutes=ready_min)),
                    ],
                    "status": "ready",
                }
            )
        out = aggregate_tat(rows)
        stages = out["per_branch_week"]["b1"][(2026, 41)]["stages"]
        assert stages["collection_to_receipt"]["median_seconds"] == pytest.approx(600.0)
        assert stages["in_process_to_ready"]["median_seconds"] == pytest.approx(4200.0)


def _insert_event_at(
    tenant: Any,
    sample: Sample,
    event_type: str,
    at: datetime,
    actor: StaffUser,
    branch: Any,
) -> None:
    """Insert a sample_event row with an exact created_at.

    sample_event is append-only (a DB trigger prohibits UPDATE), and
    created_at is auto_now_add, so backfilling goes through raw INSERT.
    """
    with tenant_context(tenant), connection.cursor() as cur:
        cur.execute(
            "INSERT INTO sample_event "
            "(id, sample_id, event, actor_id, branch_id, note, created_at) "
            "VALUES (gen_random_uuid(), %s, %s, %s, %s, NULL, %s)",
            [str(sample.id), event_type, str(actor.id), str(branch.id), at],
        )


class TestComputeTatMetricsService:
    def test_service_returns_aggregates_plus_definition(
        self, lab32_setup: dict[str, Any]
    ) -> None:
        """compute_tat_metrics(branch_id, week): DB -> pure functions ->
        aggregates + definition string."""
        from apps.reports.services import compute_tat_metrics

        s = lab32_setup
        collected = datetime(2026, 10, 6, 9, 0, tzinfo=KARACHI)  # Tue, ISO week 41
        with tenant_context(s["tenant"]):
            sample = s["sample"]
            sample.collected_at = collected
            sample.status = Sample.Status.READY
            sample.save(update_fields=["collected_at", "status", "updated_at"])
            for etype, mins in (
                ("COLLECTED", 0),
                ("RECEIVED", 15),
                ("IN_PROCESS", 45),
                ("READY", 105),
            ):
                _insert_event_at(
                    s["tenant"],
                    sample,
                    etype,
                    collected + timedelta(minutes=mins),
                    s["receptionist"],
                    s["branch"],
                )
            report = s["report"]
            report.finalised_at = collected + timedelta(minutes=150)
            report.save(update_fields=["finalised_at", "updated_at"])
            out = compute_tat_metrics(s["branch"].id, date(2026, 10, 7))
        assert "report.finalised_at" in out["definition"]
        group = out["per_branch_week"][str(s["branch"].id)][(2026, 41)]
        assert group["count"] == 1
        assert group["tat_median_seconds"] == pytest.approx(9000.0)
        stages = group["stages"]
        assert stages["collection_to_receipt"]["median_seconds"] == pytest.approx(900.0)
        assert stages["ready_to_finalised"]["median_seconds"] == pytest.approx(2700.0)

    def test_service_excludes_rejected_and_counts(
        self, lab32_setup: dict[str, Any]
    ) -> None:
        from apps.reports.services import compute_tat_metrics

        s = lab32_setup
        collected = datetime(2026, 10, 6, 9, 0, tzinfo=KARACHI)
        with tenant_context(s["tenant"]):
            sample = s["sample"]
            sample.collected_at = collected
            sample.status = Sample.Status.REJECTED
            sample.save(update_fields=["collected_at", "status", "updated_at"])
            out = compute_tat_metrics(s["branch"].id, date(2026, 10, 7))
        assert out["excluded"]["rejected"] == 1
        assert out["per_branch_week"] == {}
