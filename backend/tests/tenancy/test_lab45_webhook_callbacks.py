"""LAB-45 Test Suite: Webhook callbacks & delivery (Doc 06 §5.4, §9, §10, §12.9;
KAN-264; original LAB-67, LAB-69).

Covers:
- POST /api/v1/webhooks/n8n/notification — SENT|FAILED, hard_bounce: prefix
- POST /api/v1/webhooks/n8n/report-delivery — whatsapp_url required on
  WhatsApp SENT; OPENED never accepted; channel mismatch -> 409
- POST /api/v1/webhooks/n8n/settlement-delivery — SENT moves settlement
  APPROVED->SENT in same transaction; 409 state_conflict if not APPROVED
- Check order: path -> key -> tenant -> slug -> row -> state
  (401 unauthorized_callback, 403 tenant_slug_mismatch, 404 not_found,
  409 row_not_ready, 409 state_conflict)
- Idempotency on (idempotency_key, event): repeat same outcome -> 200,
  current state, nothing applied (CB-1)
- Beat notifications.retry_pending_deliveries: 5 retries, 30s-30m backoff,
  hard_bounce: rows skipped regardless of next_attempt_at (AU-40)
"""

import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.automation.services import (
    HARD_BOUNCE_PREFIX,
    CallbackError,
    apply_notification_callback,
    notification_backoff,
    verify_callback_key,
)
from apps.notifications.models import Notification
from apps.partners.models import Settlement
from apps.reports.models import ReportDelivery

NOTIF_URL = "/api/v1/webhooks/n8n/notification"
REPORT_URL = "/api/v1/webhooks/n8n/report-delivery"
SETTLEMENT_URL = "/api/v1/webhooks/n8n/settlement-delivery"

CALLBACK_KEY = "test-callback-key-12345"
NEXT_KEY = "test-callback-key-next-67890"


def _headers(key: str = CALLBACK_KEY) -> dict[str, str]:
    return {
        "HTTP_X_LABFLOW_CALLBACK_KEY": key,
        "HTTP_HOST": "tenant-a.localhost",
        "content_type": "application/json",
    }


def _make_notification(tenant_a: Any, **kwargs: Any) -> Notification:
    defaults = {
        "template_key": "sample_collected",
        "recipient_type": Notification.RecipientType.PATIENT,
        "channel": Notification.Channel.EMAIL,
        "status": Notification.Status.PENDING,
        "idempotency_key": "notif-key-1",
    }
    defaults.update(kwargs)
    with tenant_context(tenant_a):
        return Notification.objects.create(**defaults)


@pytest.fixture
def callback_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
    monkeypatch.setenv("N8N_CALLBACK_KEY_NEXT", NEXT_KEY)
    # Force settings re-read via override in service (reads env each call)


# ---------------------------------------------------------------------------
# Key verification (check 2)
# ---------------------------------------------------------------------------


class TestVerifyCallbackKey:
    """Check 2 via the canonical bool verifier (LAB-44, settings-based)."""

    def test_current_key_accepted(self) -> None:
        with override_settings(N8N_CALLBACK_KEY=CALLBACK_KEY, N8N_CALLBACK_KEY_NEXT=""):
            assert verify_callback_key(CALLBACK_KEY) is True

    def test_next_key_accepted_during_rotation(self) -> None:
        with override_settings(
            N8N_CALLBACK_KEY=CALLBACK_KEY, N8N_CALLBACK_KEY_NEXT=NEXT_KEY
        ):
            assert verify_callback_key(NEXT_KEY) is True

    def test_wrong_key_rejected(self) -> None:
        with override_settings(N8N_CALLBACK_KEY=CALLBACK_KEY, N8N_CALLBACK_KEY_NEXT=""):
            assert verify_callback_key("wrong-key") is False

    def test_missing_key_rejected(self) -> None:
        with override_settings(N8N_CALLBACK_KEY=CALLBACK_KEY):
            assert verify_callback_key("") is False

    def test_old_key_rejected_after_promotion(self) -> None:
        # Promotion: NEXT becomes current, old key no longer accepted
        with override_settings(N8N_CALLBACK_KEY=NEXT_KEY, N8N_CALLBACK_KEY_NEXT=""):
            assert verify_callback_key(CALLBACK_KEY) is False
            assert verify_callback_key(NEXT_KEY) is True


# ---------------------------------------------------------------------------
# Notification callback endpoint
# ---------------------------------------------------------------------------


class TestNotificationCallbackEndpoint:
    def test_sent_happy_path(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "SENT",
        }
        resp = client.post(NOTIF_URL, data=body, **_headers())
        assert resp.status_code == 200, resp.content
        data = json.loads(resp.content)
        assert data["status"] == "SENT"
        assert data["idempotency_key"] == "notif-key-1"
        with tenant_context(tenant_a):
            row = Notification.objects.get(idempotency_key="notif-key-1")
            assert row.status == Notification.Status.SENT
            assert row.next_attempt_at is None

    def test_wrong_key_401(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "SENT",
        }
        resp = client.post(NOTIF_URL, data=body, **_headers(key="bad"))
        assert resp.status_code == 401
        assert json.loads(resp.content)["error"] == "unauthorized_callback"

    def test_slug_mismatch_403(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "other-tenant",
            "idempotency_key": "notif-key-1",
            "status": "SENT",
        }
        resp = client.post(NOTIF_URL, data=body, **_headers())
        assert resp.status_code == 403
        assert json.loads(resp.content)["error"] == "tenant_slug_mismatch"

    def test_row_not_ready_409(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "no-such-key",
            "status": "SENT",
        }
        resp = client.post(NOTIF_URL, data=body, **_headers())
        assert resp.status_code == 409
        assert json.loads(resp.content)["error"] == "row_not_ready"

    def test_unknown_path_404(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        client = Client()
        resp = client.post("/api/v1/webhooks/n8n/nope", data={}, **_headers())
        assert resp.status_code == 404

    def test_replay_same_outcome_idempotent(
        self, tenant_a: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "SENT",
        }
        r1 = client.post(NOTIF_URL, data=body, **_headers())
        r2 = client.post(NOTIF_URL, data=body, **_headers())
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert json.loads(r2.content)["status"] == "SENT"

    def test_sent_on_sent_final_conflicting_failed_409(
        self, tenant_a: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        sent = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "SENT",
        }
        client.post(NOTIF_URL, data=sent, **_headers())
        failed = dict(sent, status="FAILED", last_error="452 4.2.2 full")
        resp = client.post(NOTIF_URL, data=failed, **_headers())
        assert resp.status_code == 409
        assert json.loads(resp.content)["error"] == "state_conflict"

    def test_soft_failure_sets_retry(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "FAILED",
            "last_error": "452 4.2.2 mailbox full",
        }
        resp = client.post(NOTIF_URL, data=body, **_headers())
        assert resp.status_code == 200
        with tenant_context(tenant_a):
            row = Notification.objects.get(idempotency_key="notif-key-1")
            assert row.status == Notification.Status.FAILED
            assert row.attempts == 1
            assert row.next_attempt_at is not None
            assert not row.last_error.startswith(HARD_BOUNCE_PREFIX)

    def test_hard_bounce_terminal(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "FAILED",
            "last_error": "hard_bounce:550 5.1.1 mailbox does not exist",
        }
        resp = client.post(NOTIF_URL, data=body, **_headers())
        assert resp.status_code == 200
        with tenant_context(tenant_a):
            row = Notification.objects.get(idempotency_key="notif-key-1")
            assert row.status == Notification.Status.FAILED
            assert row.next_attempt_at is None
            assert row.last_error.startswith(HARD_BOUNCE_PREFIX)

    def test_failed_requires_last_error_422(
        self, tenant_a: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "FAILED",
        }
        resp = client.post(NOTIF_URL, data=body, **_headers())
        assert resp.status_code == 422

    def test_opened_never_accepted_422(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_notification(tenant_a)
        client = Client()
        body = {
            "event": "sample.collected",
            "tenant_slug": "tenant_a",
            "idempotency_key": "notif-key-1",
            "status": "OPENED",
        }
        resp = client.post(REPORT_URL, data=body, **_headers())
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Report delivery callback endpoint
# ---------------------------------------------------------------------------


def _make_report_delivery(tenant_a: Any, **kwargs: Any) -> ReportDelivery:
    defaults = {
        "channel": ReportDelivery.Channel.EMAIL,
        "status": ReportDelivery.Status.PENDING,
        "idempotency_key": "rd-key-1",
    }
    defaults.update(kwargs)
    with tenant_context(tenant_a):
        # report FK required; create minimal report via factory if available
        from tests.factories.reports import ReportDeliveryFactory

        return ReportDeliveryFactory(**defaults)


class TestReportDeliveryCallbackEndpoint:
    def test_email_sent_happy_path(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_report_delivery(tenant_a)
        client = Client()
        body = {
            "tenant_slug": "tenant_a",
            "idempotency_key": "rd-key-1",
            "channel": "email",
            "status": "SENT",
        }
        resp = client.post(REPORT_URL, data=body, **_headers())
        assert resp.status_code == 200, resp.content
        assert json.loads(resp.content)["status"] == "SENT"

    def test_whatsapp_sent_requires_url(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_report_delivery(tenant_a, channel=ReportDelivery.Channel.WHATSAPP)
        client = Client()
        body = {
            "tenant_slug": "tenant_a",
            "idempotency_key": "rd-key-1",
            "channel": "whatsapp",
            "status": "SENT",
        }
        resp = client.post(REPORT_URL, data=body, **_headers())
        assert resp.status_code == 422
        # with URL -> 200 and stored
        body["whatsapp_url"] = "https://wa.me/123?text=hi"
        resp = client.post(REPORT_URL, data=body, **_headers())
        assert resp.status_code == 200
        with tenant_context(tenant_a):
            row = ReportDelivery.objects.get(idempotency_key="rd-key-1")
            assert row.whatsapp_url == "https://wa.me/123?text=hi"
            assert row.status == ReportDelivery.Status.SENT

    def test_channel_mismatch_409(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_report_delivery(tenant_a)  # email row
        client = Client()
        body = {
            "tenant_slug": "tenant_a",
            "idempotency_key": "rd-key-1",
            "channel": "whatsapp",
            "status": "SENT",
            "whatsapp_url": "https://wa.me/1",
        }
        resp = client.post(REPORT_URL, data=body, **_headers())
        assert resp.status_code == 409
        assert json.loads(resp.content)["error"] == "state_conflict"

    def test_hard_bounce_email_becomes_bounced(
        self, tenant_a: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_report_delivery(tenant_a)
        client = Client()
        body = {
            "tenant_slug": "tenant_a",
            "idempotency_key": "rd-key-1",
            "channel": "email",
            "status": "FAILED",
            "last_error": "hard_bounce:550 5.1.1 no such mailbox",
        }
        resp = client.post(REPORT_URL, data=body, **_headers())
        assert resp.status_code == 200
        with tenant_context(tenant_a):
            row = ReportDelivery.objects.get(idempotency_key="rd-key-1")
            assert row.status == ReportDelivery.Status.BOUNCED
            assert row.last_error.startswith(HARD_BOUNCE_PREFIX)

    def test_sent_on_bounced_409(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        _make_report_delivery(tenant_a)
        client = Client()
        bounce = {
            "tenant_slug": "tenant_a",
            "idempotency_key": "rd-key-1",
            "channel": "email",
            "status": "FAILED",
            "last_error": "hard_bounce:550 5.1.1 gone",
        }
        client.post(REPORT_URL, data=bounce, **_headers())
        sent = {
            "tenant_slug": "tenant_a",
            "idempotency_key": "rd-key-1",
            "channel": "email",
            "status": "SENT",
        }
        resp = client.post(REPORT_URL, data=sent, **_headers())
        assert resp.status_code == 409
        assert json.loads(resp.content)["error"] == "state_conflict"


# ---------------------------------------------------------------------------
# Settlement delivery callback endpoint
# ---------------------------------------------------------------------------


class TestSettlementCallbackEndpoint:
    def _make_settlement_notification(
        self, tenant_a: Any, **kwargs: Any
    ) -> tuple[Any, Notification]:
        from tests.factories.partners import (
            ReferralPartnerFactory,
            SettlementFactory,
        )

        defaults = {
            "template_key": "settlement_ready",
            "recipient_type": Notification.RecipientType.PARTNER,
            "channel": Notification.Channel.EMAIL,
            "status": Notification.Status.PENDING,
            "idempotency_key": "settle-key-1",
        }
        defaults.update(kwargs)
        with tenant_context(tenant_a):
            partner = ReferralPartnerFactory()
            settlement = SettlementFactory(
                referral_partner=partner,
                status=Settlement.Status.APPROVED,
            )
            notif = Notification.objects.create(**defaults)
            return settlement, notif

    def test_sent_moves_settlement_approved_to_sent(
        self, tenant_a: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        settlement, _ = self._make_settlement_notification(tenant_a)
        client = Client()
        body = {
            "settlement_id": str(settlement.id),
            "tenant_slug": "tenant_a",
            "idempotency_key": "settle-key-1",
            "status": "SENT",
        }
        resp = client.post(SETTLEMENT_URL, data=body, **_headers())
        assert resp.status_code == 200, resp.content
        data = json.loads(resp.content)
        assert data["settlement_status"] == "SENT"
        with tenant_context(tenant_a):
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.SENT
            notif = Notification.objects.get(idempotency_key="settle-key-1")
            assert notif.status == Notification.Status.SENT

    def test_sent_when_not_approved_409(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        settlement, _ = self._make_settlement_notification(tenant_a)
        with tenant_context(tenant_a):
            settlement.status = Settlement.Status.DRAFT
            settlement.save(update_fields=["status"])
        client = Client()
        body = {
            "settlement_id": str(settlement.id),
            "tenant_slug": "tenant_a",
            "idempotency_key": "settle-key-1",
            "status": "SENT",
        }
        resp = client.post(SETTLEMENT_URL, data=body, **_headers())
        assert resp.status_code == 409
        assert json.loads(resp.content)["error"] == "state_conflict"
        # notification row left untouched for staff inspection
        with tenant_context(tenant_a):
            notif = Notification.objects.get(idempotency_key="settle-key-1")
            assert notif.status == Notification.Status.PENDING

    def test_double_sent_idempotent(self, tenant_a: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("N8N_CALLBACK_KEY", CALLBACK_KEY)
        settlement, _ = self._make_settlement_notification(tenant_a)
        client = Client()
        body = {
            "settlement_id": str(settlement.id),
            "tenant_slug": "tenant_a",
            "idempotency_key": "settle-key-1",
            "status": "SENT",
        }
        r1 = client.post(SETTLEMENT_URL, data=body, **_headers())
        r2 = client.post(SETTLEMENT_URL, data=body, **_headers())
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert json.loads(r2.content)["settlement_status"] == "SENT"


# ---------------------------------------------------------------------------
# Retry sweep
# ---------------------------------------------------------------------------


class TestNotificationBackoff:
    def test_backoff_ladder(self) -> None:
        assert notification_backoff(1) == timedelta(seconds=30)
        assert notification_backoff(2) == timedelta(seconds=120)
        assert notification_backoff(3) == timedelta(seconds=480)
        assert notification_backoff(4) == timedelta(seconds=900)
        assert notification_backoff(5) == timedelta(seconds=1800)
        assert notification_backoff(9) == timedelta(seconds=1800)

    def test_max_attempts(self) -> None:
        from apps.automation.services import MAX_NOTIFICATION_ATTEMPTS

        assert MAX_NOTIFICATION_ATTEMPTS == 5


class TestRetrySweep:
    def test_sweep_skips_hard_bounce_even_if_due(self, tenant_a: Any) -> None:
        from apps.notifications.tasks import retry_pending_deliveries_task

        now = timezone.now()
        with tenant_context(tenant_a):
            Notification.objects.create(
                template_key="sample_collected",
                recipient_type=Notification.RecipientType.PATIENT,
                channel=Notification.Channel.EMAIL,
                status=Notification.Status.FAILED,
                attempts=1,
                next_attempt_at=now - timedelta(minutes=1),  # due!
                last_error="hard_bounce:550 5.1.1 gone",
                idempotency_key="hb-skip-1",
            )
            due_soft = Notification.objects.create(
                template_key="sample_collected",
                recipient_type=Notification.RecipientType.PATIENT,
                channel=Notification.Channel.EMAIL,
                status=Notification.Status.FAILED,
                attempts=1,
                next_attempt_at=now - timedelta(minutes=1),
                last_error="452 4.2.2 full",
                idempotency_key="soft-due-1",
            )
        with patch(
            "apps.notifications.tasks.send_notification_task.delay"
        ) as mock_delay:
            result = retry_pending_deliveries_task()
        # only the soft failure was requeued
        assert mock_delay.call_count == 1
        called_ids = [c.args[1] for c in mock_delay.call_args_list]
        assert str(due_soft.id) in called_ids
        assert result["requeued"] == 1

    def test_sweep_skips_exhausted(self, tenant_a: Any) -> None:
        from apps.notifications.tasks import retry_pending_deliveries_task

        now = timezone.now()
        with tenant_context(tenant_a):
            Notification.objects.create(
                template_key="sample_collected",
                recipient_type=Notification.RecipientType.PATIENT,
                channel=Notification.Channel.EMAIL,
                status=Notification.Status.FAILED,
                attempts=5,  # exhausted
                next_attempt_at=now - timedelta(minutes=1),
                last_error="452 4.2.2 full",
                idempotency_key="exhausted-1",
            )
        with patch(
            "apps.notifications.tasks.send_notification_task.delay"
        ) as mock_delay:
            result = retry_pending_deliveries_task()
        assert mock_delay.call_count == 0
        assert result["requeued"] == 0


# ---------------------------------------------------------------------------
# Service-level unit tests
# ---------------------------------------------------------------------------


class TestApplyNotificationCallbackService:
    def test_row_not_ready(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            with pytest.raises(CallbackError) as exc:
                apply_notification_callback(
                    idempotency_key="missing",
                    status="SENT",
                    last_error=None,
                )
            assert exc.value.error_code == "row_not_ready"
            assert exc.value.status_code == 409

    def test_failed_without_last_error_422(self, tenant_a: Any) -> None:
        _make_notification(tenant_a)
        with tenant_context(tenant_a):
            with pytest.raises(CallbackError) as exc:
                apply_notification_callback(
                    idempotency_key="notif-key-1",
                    status="FAILED",
                    last_error=None,
                )
            assert exc.value.status_code == 422

    def test_audit_row_written(self, tenant_a: Any) -> None:
        from apps.accounts.models import AuditLog

        _make_notification(tenant_a)
        with tenant_context(tenant_a):
            apply_notification_callback(
                idempotency_key="notif-key-1",
                status="SENT",
                last_error=None,
            )
            assert AuditLog.objects.filter(
                action="webhook.notification_callback"
            ).exists()
