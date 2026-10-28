from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django_tenants.utils import schema_context

from apps.core.models import Tenant
from apps.notifications.models import Notification, NotificationTemplate
from tests.factories.notifications import (
    NotificationFactory,
    NotificationTemplateFactory,
)


@pytest.mark.django_db
class TestNotificationModels:
    """
    Verifies KAN-68 (Doc 02 §5.9, §7, §8, §17, §18; Doc 06 §1.4, §9):
    - notification_template and notification exist in tenant schemas only,
      never public.
    - Composite UNIQUE uq_notification_template_key_locale_channel on
      (key, locale, channel).
    - Partial UNIQUE uq_notification_idempotency_key on (idempotency_key)
      WHERE idempotency_key IS NOT NULL: rejects duplicate non-null keys,
      allows multiple NULL idempotency_key rows.
    - Status and enum CHECK constraints enforced at the database.
    - recipient_id is a plain UUID (no FK constraint).
    """

    def test_tables_exist_in_tenant_schema_and_not_public(
        self, tenant_a: Tenant
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('notification_template', 'notification')
                """
            )
            assert cursor.fetchall() == []

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name IN ('notification_template', 'notification')
                ORDER BY table_name
                """,
                [tenant_a.schema_name],
            )
            assert [r[0] for r in cursor.fetchall()] == [
                "notification",
                "notification_template",
            ]

    def test_exact_columns_and_types(self, tenant_a: Tenant) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'notification_template'
                """,
                [tenant_a.schema_name],
            )
            nt_cols = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'notification'
                """,
                [tenant_a.schema_name],
            )
            n_cols = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

        assert set(nt_cols.keys()) == {
            "id",
            "key",
            "locale",
            "channel",
            "subject",
            "body",
            "template_context_schema",
            "created_at",
            "updated_at",
        }
        assert nt_cols["template_context_schema"] == ("jsonb", "YES")
        assert nt_cols["subject"] == ("text", "YES")

        assert set(n_cols.keys()) == {
            "id",
            "template_key",
            "recipient_type",
            "recipient_id",
            "channel",
            "status",
            "attempts",
            "next_attempt_at",
            "last_error",
            "idempotency_key",
            "created_at",
            "updated_at",
        }
        assert n_cols["recipient_id"] == ("uuid", "YES")
        assert n_cols["idempotency_key"] == ("text", "YES")

    def test_notification_template_unique_key_locale_channel(
        self, tenant_a: Tenant
    ) -> None:
        with schema_context(tenant_a.schema_name):
            NotificationTemplateFactory(
                key="report_ready",
                locale="en",
                channel="email",
            )
            # Same key + locale on different channel is allowed
            NotificationTemplateFactory(
                key="report_ready",
                locale="en",
                channel="whatsapp",
            )
            # Same key + channel on different locale (ur) is allowed
            NotificationTemplateFactory(
                key="report_ready",
                locale="ur",
                channel="email",
            )
            # Duplicate (key, locale, channel) triple fails at the DB
            with pytest.raises(IntegrityError), transaction.atomic():
                NotificationTemplate.objects.create(
                    key="report_ready",
                    locale="en",
                    channel="email",
                    subject="Dup",
                    body="Dup",
                )

    def test_notification_partial_unique_idempotency_key(
        self, tenant_a: Tenant
    ) -> None:
        with schema_context(tenant_a.schema_name):
            n1 = NotificationFactory(idempotency_key=None)
            n2 = NotificationFactory(idempotency_key=None)
            assert n1.id != n2.id

            NotificationFactory(idempotency_key="notif-fixed-key-001")
            with pytest.raises(IntegrityError), transaction.atomic():
                Notification.objects.create(
                    template_key="report_ready",
                    recipient_type="patient",
                    recipient_id=uuid.uuid4(),
                    channel="email",
                    status="PENDING",
                    idempotency_key="notif-fixed-key-001",
                )

    @pytest.mark.parametrize("bad_status", ["pending", "BOUNCED", "OPENED", ""])
    def test_notification_status_check_constraint(
        self, tenant_a: Tenant, bad_status: str
    ) -> None:
        with (
            schema_context(tenant_a.schema_name),
            pytest.raises(IntegrityError),
            transaction.atomic(),
        ):
            Notification.objects.create(
                template_key="report_ready",
                recipient_type="patient",
                recipient_id=uuid.uuid4(),
                channel="email",
                status=bad_status,
            )

    def test_indexes_exist_in_pg_indexes(self, tenant_a: Tenant) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s
                  AND tablename IN ('notification_template', 'notification')
                """,
                [tenant_a.schema_name],
            )
            index_names = {row[0] for row in cursor.fetchall()}

        assert "uq_notification_template_key_locale_channel" in index_names
        assert "uq_notification_idempotency_key" in index_names
