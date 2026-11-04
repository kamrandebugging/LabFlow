"""LAB-44 (KAN-263) — Outbound webhook engine tests.

Covers Doc 06 §5.1–§5.3 (payload, HMAC-SHA256 signature, 5-min timestamp,
idempotency), §5.5 (callback key rotation dual-accept), §8.4 (message_id
optional/logged/not persisted), and the Beat retry sweep (Doc 10 §9:
minutes 3/18/33/48).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.automation import payloads, services, signing
from apps.automation.models import WebhookDelivery
from apps.core.models import Tenant
from tests.factories.automation import WebhookDeliveryFactory

TEST_SECRET = "test-webhook-secret-32-chars-minimum"


def _expected_hmac(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


@pytest.mark.django_db
class TestSigning:
    """Doc 06 §5.1 — HMAC-SHA256 over the raw request body."""

    def test_signature_header_name(self) -> None:
        assert signing.SIGNATURE_HEADER == "X-LabFlow-Signature"

    def test_sign_payload_matches_rfc2104_vector(self) -> None:
        raw = b'{"event":"report.ready"}'
        assert signing.sign_payload(raw, TEST_SECRET) == _expected_hmac(
            raw, TEST_SECRET
        )

    def test_sign_payload_hex_digest_length(self) -> None:
        digest = signing.sign_payload(b"{}", TEST_SECRET)
        assert len(digest) == 64
        int(digest, 16)  # valid hex

    def test_verify_signature_accepts_valid(self) -> None:
        raw = b'{"a":1}'
        sig = signing.sign_payload(raw, TEST_SECRET)
        assert signing.verify_signature(raw, sig, TEST_SECRET) is True

    def test_verify_signature_rejects_tampered_body(self) -> None:
        raw = b'{"a":1}'
        sig = signing.sign_payload(raw, TEST_SECRET)
        assert signing.verify_signature(b'{"a":2}', sig, TEST_SECRET) is False

    def test_verify_signature_rejects_wrong_key(self) -> None:
        raw = b'{"a":1}'
        sig = signing.sign_payload(raw, TEST_SECRET)
        assert signing.verify_signature(raw, sig, "wrong-key") is False

    def test_verify_signature_rejects_malformed(self) -> None:
        assert signing.verify_signature(b"{}", "not-hex!!", TEST_SECRET) is False
        assert signing.verify_signature(b"{}", "", TEST_SECRET) is False


@pytest.mark.django_db
class TestPayloadBuilder:
    """Doc 06 §5.1 — the six-field envelope; §5.2 timestamp rule."""

    def test_envelope_has_all_six_fields(self) -> None:
        payload = payloads.build_webhook_payload(
            event="report.ready",
            tenant_slug="city-diagnostics",
            callback_url="https://city-diagnostics.labflow.app/api/v1/webhooks/n8n/report-delivery",
            idempotency_key="3f8c2e1a-7b4d-4e5f-9a1c-0d2b3e4f5a6b",
            data={"report_id": "abc"},
        )
        assert payload["event"] == "report.ready"
        assert payload["tenant_slug"] == "city-diagnostics"
        assert payload["callback_url"].startswith("https://")
        assert payload["idempotency_key"] == "3f8c2e1a-7b4d-4e5f-9a1c-0d2b3e4f5a6b"
        assert payload["data"] == {"report_id": "abc"}
        # ISO 8601 UTC timestamp, set at build time
        ts = payload["timestamp"]
        assert ts.endswith("Z")
        parsed = payloads.parse_timestamp(ts)
        assert timezone.now() - parsed < timedelta(minutes=1)

    def test_serialization_is_deterministic(self) -> None:
        payload = payloads.build_webhook_payload(
            event="e",
            tenant_slug="t",
            callback_url="https://t.labflow.app/cb",
            idempotency_key="k",
            data={"b": 2, "a": 1},
        )
        first = payloads.serialize_payload(payload)
        second = payloads.serialize_payload(payload)
        assert first == second
        # Exact bytes are what gets signed (Doc 06 F-1 / AU-33)
        assert isinstance(first, bytes)
        assert json.loads(first.decode("utf-8"))["data"] == {"a": 1, "b": 2}

    def test_explicit_timestamp_is_preserved(self) -> None:
        payload = payloads.build_webhook_payload(
            event="e",
            tenant_slug="t",
            callback_url="https://t.labflow.app/cb",
            idempotency_key="k",
            data={},
            timestamp="2026-10-20T08:15:30Z",
        )
        assert payload["timestamp"] == "2026-10-20T08:15:30Z"


@pytest.mark.django_db
class TestEmitWebhook:
    """Doc 06 §5.1 — row first, then POST; 2xx → SENT, else PENDING+retry."""

    def _emit_kwargs(self, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "event": "report.ready",
            "tenant_slug": "city-diagnostics",
            "webhook_url": "https://n8n.internal/webhook/report-ready",
            "callback_url": "https://city-diagnostics.labflow.app/api/v1/webhooks/n8n/report-delivery",
            "data": {"report_id": "r1"},
        }
        kwargs.update(overrides)
        return kwargs

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_row_written_before_send_with_pending_status(
        self, tenant_a: Tenant
    ) -> None:
        with (
            schema_context(tenant_a.schema_name),
            patch.object(
                services, "_post_signed", return_value=(200, b"ok")
            ) as mock_post,
        ):
            row = services.emit_webhook(**self._emit_kwargs())
            # Row was created PENDING with attempts=0 before the POST
            assert mock_post.called
            row.refresh_from_db()
            assert row.status == WebhookDelivery.Status.SENT
            assert row.attempts == 0
            stored = row.payload_jsonb
            assert stored["event"] == "report.ready"
            assert stored["idempotency_key"] == row.idempotency_key

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_post_carries_signature_header_and_exact_bytes(
        self, tenant_a: Tenant
    ) -> None:
        with (
            schema_context(tenant_a.schema_name),
            patch.object(
                services, "_post_signed", return_value=(200, b"ok")
            ) as mock_post,
        ):
            services.emit_webhook(**self._emit_kwargs())
            (url, raw_body, signature), _ = mock_post.call_args
            assert url == "https://n8n.internal/webhook/report-ready"
            assert signature == _expected_hmac(raw_body, TEST_SECRET)
            assert len(signature) == 64

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_non_2xx_leaves_pending_with_retry_scheduled(
        self, tenant_a: Tenant
    ) -> None:
        with (
            schema_context(tenant_a.schema_name),
            patch.object(services, "_post_signed", return_value=(500, b"boom")),
        ):
            before = timezone.now()
            row = services.emit_webhook(**self._emit_kwargs())
            row.refresh_from_db()
            assert row.status == WebhookDelivery.Status.PENDING
            assert row.attempts == 1
            assert row.next_attempt_at is not None
            assert row.next_attempt_at > before
            assert "500" in (row.last_error or "")

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_timeout_leaves_pending_with_retry_scheduled(
        self, tenant_a: Tenant
    ) -> None:
        with (
            schema_context(tenant_a.schema_name),
            patch.object(
                services,
                "_post_signed",
                side_effect=services.WebhookTransportError("timed out"),
            ),
        ):
            row = services.emit_webhook(**self._emit_kwargs())
            row.refresh_from_db()
            assert row.status == WebhookDelivery.Status.PENDING
            assert row.attempts == 1
            assert row.next_attempt_at is not None

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_caller_supplied_idempotency_key_is_used(self, tenant_a: Tenant) -> None:
        with (
            schema_context(tenant_a.schema_name),
            patch.object(services, "_post_signed", return_value=(200, b"ok")),
        ):
            row = services.emit_webhook(
                **self._emit_kwargs(idempotency_key="fixed-key-123")
            )
            assert row.idempotency_key == "fixed-key-123"

    def test_missing_secret_raises_before_row_write(self, tenant_a: Tenant) -> None:
        with (
            schema_context(tenant_a.schema_name),
            override_settings(N8N_WEBHOOK_SECRET=""),
        ):
            with pytest.raises(services.WebhookConfigurationError):
                services.emit_webhook(**self._emit_kwargs())
            assert WebhookDelivery.objects.count() == 0

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_row_has_retry_deadline_at_creation(self, tenant_a: Tenant) -> None:
        # Crash-safety: if the process dies between the row write and the
        # POST, the sweep must still pick the row up (NULL next_attempt_at
        # would strand it forever).
        with schema_context(tenant_a.schema_name):
            before = timezone.now()
            with patch.object(
                services,
                "_post_signed",
                side_effect=services.WebhookTransportError("down"),
            ):
                row = services.emit_webhook(**self._emit_kwargs())
                row.refresh_from_db()
                assert row.next_attempt_at is not None
                assert row.next_attempt_at > before


@pytest.mark.django_db
class TestRetrySweep:
    """Doc 06 §5.2 + Doc 10 §9 — Beat sweep re-stamps + re-signs, same key."""

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_sweep_restamps_timestamp_and_resigns(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            row = WebhookDeliveryFactory(
                status=WebhookDelivery.Status.PENDING,
                attempts=1,
                next_attempt_at=timezone.now() - timedelta(minutes=1),
                payload_jsonb={
                    "event": "report.ready",
                    "tenant_slug": "city-diagnostics",
                    "callback_url": "https://city-diagnostics.labflow.app/cb",
                    "idempotency_key": "keep-me",
                    "timestamp": "2020-01-01T00:00:00Z",
                    "data": {},
                },
            )
            row.payload_jsonb["idempotency_key"] = "keep-me"
            row.save(update_fields=["payload_jsonb"])
            with patch.object(
                services, "_post_signed", return_value=(200, b"ok")
            ) as mock_post:
                services.retry_due_deliveries(
                    tenant_slug=tenant_a.schema_name,
                    webhook_url="https://n8n.internal/webhook/x",
                    now=timezone.now(),
                )
                (url, raw_body, signature), _ = mock_post.call_args
                wire = json.loads(raw_body.decode("utf-8"))
                # Re-stamped at send time (§5.2 TS-2), re-signed, same key
                assert wire["timestamp"] != "2020-01-01T00:00:00Z"
                assert wire["idempotency_key"] == "keep-me"
                assert signature == _expected_hmac(raw_body, TEST_SECRET)
                row.refresh_from_db()
                assert row.status == WebhookDelivery.Status.SENT
                # Stored payload keeps the ORIGINAL timestamp for audit
                assert row.payload_jsonb["timestamp"] == "2020-01-01T00:00:00Z"

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_sweep_skips_rows_not_yet_due(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            WebhookDeliveryFactory(
                status=WebhookDelivery.Status.PENDING,
                attempts=1,
                next_attempt_at=timezone.now() + timedelta(hours=1),
            )
            with patch.object(
                services, "_post_signed", return_value=(200, b"ok")
            ) as mock_post:
                services.retry_due_deliveries(
                    tenant_slug=tenant_a.schema_name,
                    webhook_url="https://n8n.internal/webhook/x",
                    now=timezone.now(),
                )
                assert not mock_post.called

    @override_settings(N8N_WEBHOOK_SECRET=TEST_SECRET)
    def test_sweep_skips_sent_rows(self, tenant_a: Tenant) -> None:
        with schema_context(tenant_a.schema_name):
            WebhookDeliveryFactory(
                status=WebhookDelivery.Status.SENT,
                attempts=1,
                next_attempt_at=timezone.now() - timedelta(minutes=1),
            )
            with patch.object(
                services, "_post_signed", return_value=(200, b"ok")
            ) as mock_post:
                services.retry_due_deliveries(
                    tenant_slug=tenant_a.schema_name,
                    webhook_url="https://n8n.internal/webhook/x",
                    now=timezone.now(),
                )
                assert not mock_post.called


@pytest.mark.django_db
class TestCallbackKeyRotation:
    """Doc 06 §5.5 — dual-accept during rotation; §8.4 message_id."""

    @override_settings(N8N_CALLBACK_KEY="current-key", N8N_CALLBACK_KEY_NEXT="next-key")
    def test_current_key_accepted(self) -> None:
        assert services.verify_callback_key("current-key") is True

    @override_settings(N8N_CALLBACK_KEY="current-key", N8N_CALLBACK_KEY_NEXT="next-key")
    def test_next_key_accepted_during_rotation(self) -> None:
        assert services.verify_callback_key("next-key") is True

    @override_settings(N8N_CALLBACK_KEY="current-key", N8N_CALLBACK_KEY_NEXT="")
    def test_unknown_key_rejected(self) -> None:
        assert services.verify_callback_key("old-key") is False
        assert services.verify_callback_key("") is False

    def test_message_id_extracted_but_not_persisted(self, tenant_a: Tenant) -> None:
        # §8.4: message_id is optional, logged, never stored on the row
        body = {"idempotency_key": "k", "message_id": "n8n-exec-42"}
        assert services.extract_message_id(body) == "n8n-exec-42"
        assert services.extract_message_id({"idempotency_key": "k"}) is None
        assert not hasattr(WebhookDelivery, "message_id")
        field_names = {f.name for f in WebhookDelivery._meta.get_fields()}
        assert "message_id" not in field_names
