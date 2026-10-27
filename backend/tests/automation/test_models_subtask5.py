from __future__ import annotations

import pytest
from django.db import IntegrityError, connection, transaction
from django_tenants.utils import schema_context

from apps.automation.models import WebhookDelivery
from apps.core.models import Tenant
from tests.factories.automation import WebhookDeliveryFactory


@pytest.mark.django_db
class TestWebhookDeliveryModel:
    """
    Verifies KAN-69 (Doc 02 §5.10, §7, §8, §18; Doc 06 §1.4, §5.1):
    - webhook_delivery exists in tenant schemas only, never public.
    - Exact column set and types: payload_jsonb is PostgreSQL jsonb NOT NULL;
      idempotency_key is text NOT NULL.
    - Full (non-partial) UNIQUE constraint uq_webhook_delivery_idempotency_key
      on idempotency_key.
    - Partial retry index idx_webhook_delivery_status_next_attempt_at
      WHERE status IN ('PENDING','FAILED').
    - Status CHECK constraint chk_webhook_delivery_status
      on ('PENDING', 'SENT', 'FAILED').
    """

    def test_table_exists_in_tenant_schema_and_not_public(
        self, tenant_a: Tenant
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'webhook_delivery'
                """
            )
            assert cursor.fetchall() == []

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = 'webhook_delivery'
                """,
                [tenant_a.schema_name],
            )
            assert [r[0] for r in cursor.fetchall()] == ["webhook_delivery"]

    def test_exact_columns_and_jsonb_type(self, tenant_a: Tenant) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'webhook_delivery'
                """,
                [tenant_a.schema_name],
            )
            cols = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

        assert "tenant_id" not in cols
        assert "tenant" not in cols
        assert set(cols.keys()) == {
            "id",
            "event",
            "idempotency_key",
            "payload_jsonb",
            "status",
            "attempts",
            "next_attempt_at",
            "last_error",
            "created_at",
            "updated_at",
        }
        assert cols["idempotency_key"] == ("text", "NO")
        assert cols["payload_jsonb"] == ("jsonb", "NO")
        assert cols["status"] == ("text", "NO")
        assert cols["attempts"] == ("integer", "NO")
        assert cols["next_attempt_at"][1] == "YES"
        assert cols["last_error"] == ("text", "YES")

    def test_full_unique_idempotency_key_and_faithful_jsonb_roundtrip(
        self, tenant_a: Tenant
    ) -> None:
        payload = {
            "event": "settlement.approved",
            "tenant_slug": "city-diagnostics",
            "callback_url": (
                "https://city-diagnostics.labflow.app/api/v1/webhooks/n8n/settlement-delivery"
            ),
            "idempotency_key": "3f8c2e1a-7b4d-4e5f-9a1c-0d2b3e4f5a6b",
            "timestamp": "2026-10-20T08:15:30Z",
            "data": {"settlement_id": "11111111-2222-3333-4444-555555555555"},
        }
        with schema_context(tenant_a.schema_name):
            wd = WebhookDeliveryFactory(
                event="settlement.approved",
                idempotency_key="3f8c2e1a-7b4d-4e5f-9a1c-0d2b3e4f5a6b",
                payload_jsonb=payload,
            )
            wd.refresh_from_db()
            assert wd.payload_jsonb == payload

            # Duplicate idempotency_key fails at the database
            with pytest.raises(IntegrityError), transaction.atomic():
                WebhookDelivery.objects.create(
                    event="settlement.approved",
                    idempotency_key="3f8c2e1a-7b4d-4e5f-9a1c-0d2b3e4f5a6b",
                    payload_jsonb=payload,
                    status="PENDING",
                )

    @pytest.mark.parametrize("bad_status", ["pending", "BOUNCED", "OPENED", ""])
    def test_status_check_constraint_rejects_invalid_values(
        self, tenant_a: Tenant, bad_status: str
    ) -> None:
        with (
            schema_context(tenant_a.schema_name),
            pytest.raises(IntegrityError),
            transaction.atomic(),
        ):
            WebhookDelivery.objects.create(
                event="report.ready",
                idempotency_key="webhook-bad-status-key",
                payload_jsonb={"event": "report.ready"},
                status=bad_status,
            )

    def test_indexes_exist_in_pg_indexes_and_unique_is_not_partial(
        self, tenant_a: Tenant
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = %s
                  AND tablename = 'webhook_delivery'
                """,
                [tenant_a.schema_name],
            )
            indexes = {row[0]: row[1] for row in cursor.fetchall()}

        assert "uq_webhook_delivery_idempotency_key" in indexes
        assert "WHERE" not in indexes["uq_webhook_delivery_idempotency_key"]

        assert "idx_webhook_delivery_status_next_attempt_at" in indexes
        assert "WHERE" in indexes["idx_webhook_delivery_status_next_attempt_at"]
