"""LAB-43 (KAN-262): Settlement delivery tests.

Covers Doc 05 §9 (DL-1..DL-7), §7.7 (ST-21), RS-41:
- dispatch creates notification row (template_key='settlement_ready',
  recipient_type='partner', channel='email', PENDING) + webhook_delivery row
- partner_email_missing -> notification FAILED, settlement stays APPROVED
- SENT set by callback only (never assumed at send time)
- retry sweep: 15-min beat, 5 attempts, 30s->30min backoff, exhausted ->
  FAILED stays, settlement stays APPROVED, Sentry alert
- re-send creates FRESH notification row; SENT re-send = copy
- statement.pdf always downloadable (DL-7)
- POST /settlements/{id}/send: 422 partner_email_missing, Owner only
"""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role, StaffUser
from apps.automation.models import WebhookDelivery
from apps.core.models import Tenant
from apps.notifications.models import Notification
from apps.partners.delivery import (
    DELIVERY_MAX_ATTEMPTS,
    SettlementDeliveryError,
    dispatch_settlement_delivery,
    handle_delivery_callback,
)
from apps.partners.models import ReferralPartner, Settlement
from tests.factories.accounts import StaffUserFactory
from tests.factories.branches import BranchFactory
from tests.factories.partners import ReferralPartnerFactory, SettlementFactory

TENANT_HOST = "tenant-a.localhost"


def _auth_headers(user: StaffUser, tenant_id: str = "tenant_a") -> dict[str, str]:
    session = AuthService.create_session(user=user, tenant_id=tenant_id)
    slug = tenant_id.replace("_", "-")
    return {
        "Authorization": f"Bearer {session['access']}",
        "Host": f"{slug}.localhost",
    }


def _post(client: Client, user: StaffUser, url: str) -> Any:
    return client.post(
        url,
        data=json.dumps({}),
        content_type="application/json",
        headers=_auth_headers(user),
    )


def _get(client: Client, user: StaffUser, url: str) -> Any:
    return client.get(url, headers=_auth_headers(user))


def _make_owner(tenant: Tenant) -> StaffUser:
    branch = BranchFactory()
    return cast(StaffUser, StaffUserFactory(branch=branch, role=Role.OWNER))


def _make_settlement(partner: ReferralPartner, **kwargs: Any) -> Settlement:
    """Typed wrapper: factory_boy stubs return the factory type."""
    return cast(
        Settlement,
        SettlementFactory(referral_partner=partner, **kwargs),
    )


def _make_partner(**kwargs: Any) -> ReferralPartner:
    """Typed wrapper: factory_boy stubs return the factory type."""
    return cast(ReferralPartner, ReferralPartnerFactory(**kwargs))


@pytest.mark.django_db
class TestDispatchSettlementDelivery:
    """DL-2, DL-3: dispatch writes notification + webhook rows, PENDING."""

    def test_dispatch_creates_pending_notification_and_webhook(
        self, tenant_a: Tenant
    ) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)

            notif = dispatch_settlement_delivery(settlement, actor=owner)

            assert notif.template_key == "settlement_ready"
            assert notif.recipient_type == Notification.RecipientType.PARTNER
            assert notif.recipient_id == partner.id
            assert notif.channel == Notification.Channel.EMAIL
            assert notif.status == Notification.Status.PENDING
            assert notif.attempts == 0

            hook = WebhookDelivery.objects.get(idempotency_key=notif.idempotency_key)
            assert hook.event == "settlement.delivery_requested"
            assert hook.status == WebhookDelivery.Status.PENDING
            payload = hook.payload_jsonb
            assert payload["tenant_slug"] == tenant_a.schema_name
            assert payload["data"]["settlement_id"] == str(settlement.id)

            # Settlement NOT moved to SENT at dispatch — callback only (DL-3).
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.APPROVED

    def test_dispatch_requires_approved_status(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.DRAFT)
            with pytest.raises(SettlementDeliveryError) as exc:
                dispatch_settlement_delivery(settlement, actor=owner)
            assert exc.value.error_code == "invalid_state_transition"

    def test_dispatch_idempotent_per_attempt_series(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            n1 = dispatch_settlement_delivery(settlement, actor=owner)
            n2 = dispatch_settlement_delivery(settlement, actor=owner)
            assert n1.id == n2.id
            assert (
                Notification.objects.filter(
                    template_key="settlement_ready",
                    recipient_id=partner.id,
                ).count()
                == 1
            )


@pytest.mark.django_db
class TestPartnerEmailMissing:
    """ST-21, RS-41: missing email -> FAILED notification, stays APPROVED."""

    def test_missing_email_records_failed_notification(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email=None)
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)

            notif = dispatch_settlement_delivery(settlement, actor=owner)

            assert notif.status == Notification.Status.FAILED
            assert notif.last_error == "partner_email_missing"
            # No webhook row for a send that can never happen.
            assert (
                WebhookDelivery.objects.filter(
                    idempotency_key=notif.idempotency_key
                ).count()
                == 0
            )
            # Approval is real; only the sending failed (ST-21).
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.APPROVED

    def test_blank_email_treated_as_missing(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="   ")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            notif = dispatch_settlement_delivery(settlement, actor=owner)
            assert notif.status == Notification.Status.FAILED
            assert notif.last_error == "partner_email_missing"


@pytest.mark.django_db
class TestDeliveryCallback:
    """DL-3: SENT set by callback only."""

    def _signed_payload(
        self, tenant: Tenant, notif: Notification
    ) -> tuple[dict[str, Any], str]:
        from apps.partners.delivery import _sign_payload

        body = {
            "tenant_slug": tenant.schema_name,
            "idempotency_key": notif.idempotency_key,
            "status": "delivered",
            "timestamp": int(timezone.now().timestamp()),
        }
        sig = _sign_payload(body)
        return body, sig

    def test_callback_marks_sent_and_moves_settlement(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            notif = dispatch_settlement_delivery(settlement, actor=owner)

            body, sig = self._signed_payload(tenant_a, notif)
            result = handle_delivery_callback(tenant_a.schema_name, body, signature=sig)

            assert result["status"] == "ok"
            notif.refresh_from_db()
            assert notif.status == Notification.Status.SENT
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.SENT

    def test_callback_rejects_bad_signature(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            notif = dispatch_settlement_delivery(settlement, actor=owner)
            body, _ = self._signed_payload(tenant_a, notif)
            with pytest.raises(SettlementDeliveryError) as exc:
                handle_delivery_callback(
                    tenant_a.schema_name, body, signature="bad-signature"
                )
            assert exc.value.error_code == "invalid_signature"
            notif.refresh_from_db()
            assert notif.status == Notification.Status.PENDING

    def test_callback_rejects_tenant_mismatch(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            notif = dispatch_settlement_delivery(settlement, actor=owner)
            body, sig = self._signed_payload(tenant_a, notif)
            with pytest.raises(SettlementDeliveryError) as exc:
                handle_delivery_callback("other_tenant", body, signature=sig)
            assert exc.value.error_code == "tenant_mismatch"


@pytest.mark.django_db
class TestRetrySweep:
    """DL-5: 15-min beat retries FAILED rows; 5 attempts max; never un-approves."""

    def test_sweep_requeues_due_failed_rows(self, tenant_a: Tenant) -> None:
        from apps.partners.tasks import retry_failed_settlement_deliveries

        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            notif = dispatch_settlement_delivery(settlement, actor=owner)
            notif.status = Notification.Status.FAILED
            notif.attempts = 1
            notif.next_attempt_at = timezone.now() - timezone.timedelta(seconds=1)
            notif.last_error = "n8n timeout"
            notif.save(
                update_fields=[
                    "status",
                    "attempts",
                    "next_attempt_at",
                    "last_error",
                    "updated_at",
                ]
            )

            with patch(
                "apps.partners.tasks.deliver_settlement_task.delay"
            ) as mock_delay:
                result = retry_failed_settlement_deliveries()

            assert result["requeued"] >= 1
            mock_delay.assert_called()
            notif.refresh_from_db()
            # Claimed: lease pushed out so overlapping beats don't double-send.
            assert notif.next_attempt_at > timezone.now()

    def test_sweep_skips_exhausted_rows(self, tenant_a: Tenant) -> None:
        from apps.partners.tasks import retry_failed_settlement_deliveries

        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            notif = dispatch_settlement_delivery(settlement, actor=owner)
            notif.status = Notification.Status.FAILED
            notif.attempts = DELIVERY_MAX_ATTEMPTS
            notif.next_attempt_at = timezone.now() - timezone.timedelta(seconds=1)
            notif.save(update_fields=["status", "attempts", "next_attempt_at"])

            with patch(
                "apps.partners.tasks.deliver_settlement_task.delay"
            ) as mock_delay:
                retry_failed_settlement_deliveries()

            mock_delay.assert_not_called()
            # Settlement stays APPROVED — a delivery failure never un-approves.
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.APPROVED

    def test_deliver_task_exhaustion_marks_failed_and_alerts(
        self, tenant_a: Tenant
    ) -> None:
        from apps.partners.tasks import deliver_settlement_task

        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            notif = dispatch_settlement_delivery(settlement, actor=owner)
            notif.attempts = DELIVERY_MAX_ATTEMPTS - 1
            notif.save(update_fields=["attempts"])

            with (
                override_settings(N8N_WEBHOOK_URL="http://n8n.test/hook"),
                patch(
                    "apps.partners.tasks._post_to_n8n",
                    side_effect=ConnectionError("n8n down"),
                ),
                patch("apps.partners.delivery.logger") as mock_logger,
            ):
                deliver_settlement_task(tenant_a.schema_name, str(notif.id))

            notif.refresh_from_db()
            assert notif.status == Notification.Status.FAILED
            assert notif.attempts == DELIVERY_MAX_ATTEMPTS
            assert notif.last_error is not None
            # Sentry alert path: error logged.
            assert mock_logger.error.called
            settlement.refresh_from_db()
            assert settlement.status == Settlement.Status.APPROVED


@pytest.mark.django_db
class TestResendEndpoint:
    """DL-6: re-send creates a FRESH row; SENT re-send = copy."""

    def test_resend_creates_fresh_notification_row(self, tenant_a: Tenant) -> None:
        client = Client()
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            first = dispatch_settlement_delivery(settlement, actor=owner)
            first.status = Notification.Status.FAILED
            first.last_error = "n8n timeout"
            first.save(update_fields=["status", "last_error"])

            resp = _post(client, owner, f"/api/v1/settlements/{settlement.id}/send")

            assert resp.status_code == 200, resp.content[:200]
            rows = Notification.objects.filter(
                template_key="settlement_ready",
                recipient_id=partner.id,
            )
            assert rows.count() == 2
            # The failed row stays as the record of the failure.
            assert rows.filter(status=Notification.Status.FAILED).count() == 1
            assert rows.filter(status=Notification.Status.PENDING).count() == 1

    def test_resend_sent_settlement_sends_copy(self, tenant_a: Tenant) -> None:
        client = Client()
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.SENT)
            resp = _post(client, owner, f"/api/v1/settlements/{settlement.id}/send")
            assert resp.status_code == 200, resp.content[:200]
            copy_row = (
                Notification.objects.filter(
                    template_key="settlement_ready",
                    recipient_id=partner.id,
                )
                .order_by("-created_at")
                .first()
            )
            assert copy_row is not None
            hook = WebhookDelivery.objects.get(idempotency_key=copy_row.idempotency_key)
            assert hook.payload_jsonb["data"]["is_copy"] is True

    def test_resend_rejected_for_draft(self, tenant_a: Tenant) -> None:
        client = Client()
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.DRAFT)
            resp = _post(client, owner, f"/api/v1/settlements/{settlement.id}/send")
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "invalid_state_transition"

    def test_send_missing_email_returns_422(self, tenant_a: Tenant) -> None:
        client = Client()
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email=None)
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            resp = _post(client, owner, f"/api/v1/settlements/{settlement.id}/send")
            assert resp.status_code == 422
            assert resp.json()["error"]["code"] == "partner_email_missing"

    def test_send_forbidden_for_non_owner(self, tenant_a: Tenant) -> None:
        client = Client()
        with schema_context(tenant_a.schema_name):
            branch = BranchFactory()
            manager = cast(
                StaffUser, StaffUserFactory(branch=branch, role=Role.MANAGER)
            )
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(partner, status=Settlement.Status.APPROVED)
            resp = _post(client, manager, f"/api/v1/settlements/{settlement.id}/send")
            assert resp.status_code == 403


@pytest.mark.django_db
class TestStatementPdfDownload:
    """DL-7: delivery trouble never locks the lab out of its own document."""

    def test_statement_downloadable_when_delivery_failed(
        self, tenant_a: Tenant
    ) -> None:
        from django.core.files.storage import default_storage

        client = Client()
        pdf_key = f"settlements/{uuid.uuid4()}/statement.pdf"
        pdf_bytes = b"%PDF-1.4 fake statement"
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email=None)
            settlement = _make_settlement(
                partner,
                status=Settlement.Status.APPROVED,
                statement_pdf_key=pdf_key,
            )
            # Delivery failed (no email) — PDF must still be downloadable.
            dispatch_settlement_delivery(settlement, actor=owner)
            default_storage.save(
                pdf_key,
                __import__(
                    "django.core.files.base", fromlist=["ContentFile"]
                ).ContentFile(pdf_bytes),
            )
            try:
                resp = _get(
                    client, owner, f"/api/v1/settlements/{settlement.id}/statement.pdf"
                )
                assert resp.status_code == 200
                assert resp["Content-Type"] == "application/pdf"
                assert b"".join(resp.streaming_content) == pdf_bytes
            finally:
                default_storage.delete(pdf_key)

    def test_statement_download_404_without_pdf(self, tenant_a: Tenant) -> None:
        client = Client()
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email="doc@example.com")
            settlement = _make_settlement(
                partner,
                status=Settlement.Status.APPROVED,
                statement_pdf_key=None,
            )
            resp = _get(
                client, owner, f"/api/v1/settlements/{settlement.id}/statement.pdf"
            )
            assert resp.status_code == 404


@pytest.mark.django_db
class TestExceptionsEndpoint:
    """Rehearsal support: drafts badge data on /exceptions."""

    def test_exceptions_reports_drafts_and_failed_deliveries(
        self, tenant_a: Tenant
    ) -> None:
        client = Client()
        with schema_context(tenant_a.schema_name):
            owner = _make_owner(tenant_a)
            partner = _make_partner(email=None)
            SettlementFactory(referral_partner=partner, status=Settlement.Status.DRAFT)
            approved = _make_settlement(partner, status=Settlement.Status.APPROVED)
            dispatch_settlement_delivery(approved, actor=owner)

            resp = _get(client, owner, "/api/v1/settlements/exceptions")
            assert resp.status_code == 200, resp.content[:200]
            data = resp.json()
            assert data["drafts_awaiting_approval"] == 1
            assert data["failed_deliveries"] == 1
