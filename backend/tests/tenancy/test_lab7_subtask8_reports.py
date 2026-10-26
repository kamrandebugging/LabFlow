from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.reports.models import (
    Report,
    ReportAccessToken,
    ReportDelivery,
    ReportVersion,
)
from tests.factories.accounts import StaffUserFactory
from tests.factories.reports import (
    ReportAccessTokenFactory,
    ReportDeliveryFactory,
    ReportFactory,
    ReportVersionFactory,
)
from tests.factories.samples import SampleFactory


@pytest.mark.django_db
class TestReportModelsSchemaAndConstraints:
    def test_report_tables_columns_and_indexes_exist(self, tenant_a: Any) -> None:
        expected_indexes = {
            "report": {"idx_report_sample_id"},
            "report_version": {
                "uq_report_version_report_id_version",
                "uq_report_version_pdf_key",
                "idx_report_version_report_id",
                "idx_report_version_generated_by",
            },
            "report_delivery": {
                "idx_report_delivery_report_id",
                "idx_report_delivery_status_next_attempt_at",
            },
            "report_access_token": {
                "uq_report_access_token_token_hash",
                "idx_report_access_token_report_id",
            },
        }
        with tenant_context(tenant_a), connection.cursor() as cursor:
            for table_name, idx_set in expected_indexes.items():
                cursor.execute(
                    """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = %s AND tablename = %s;
                        """,
                    [tenant_a.schema_name, table_name],
                )
                rows = {r[0]: r[1] for r in cursor.fetchall()}
                for expected_idx in idx_set:
                    assert expected_idx in rows, (
                        f"Missing index {expected_idx} on {table_name}"
                    )
                if table_name == "report_delivery":
                    idx_def = rows["idx_report_delivery_status_next_attempt_at"]
                    assert "WHERE" in idx_def
                    assert "PENDING" in idx_def
                    assert "FAILED" in idx_def

            # Verify report_version is append-only (created_at only)
            cursor.execute(
                """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = 'report_version';
                    """,
                [tenant_a.schema_name],
            )
            rv_cols = {r[0] for r in cursor.fetchall()}
            assert rv_cols == {
                "id",
                "report_id",
                "version",
                "pdf_key",
                "generated_by",
                "created_at",
            }
            assert "updated_at" not in rv_cols
            assert "deleted_at" not in rv_cols

            # Verify report_access_token has token_hash only
            # and no plain token column
            cursor.execute(
                """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = 'report_access_token';
                    """,
                [tenant_a.schema_name],
            )
            rat_cols = {r[0] for r in cursor.fetchall()}
            assert rat_cols == {
                "id",
                "report_id",
                "token_hash",
                "expires_at",
                "revoked_at",
                "last_accessed_at",
                "created_at",
                "updated_at",
            }
            assert "token" not in rat_cols
            assert "plain_token" not in rat_cols
            assert "deleted_at" not in rat_cols

    def test_report_and_report_delivery_status_and_channel_checks(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            sample = SampleFactory()

            for valid_status in (
                Report.Status.DRAFT,
                Report.Status.FINAL,
                Report.Status.AMENDED,
                Report.Status.VOID,
            ):
                rep = ReportFactory(sample=sample, status=valid_status)
                assert rep.status == valid_status

            # Invalid report status fails at DB -> chk_report_status
            with pytest.raises(IntegrityError), transaction.atomic():
                Report.objects.create(
                    sample=sample,
                    status="cancelled_invalid",
                )

            rep = ReportFactory(sample=sample)
            for valid_channel in (
                ReportDelivery.Channel.EMAIL,
                ReportDelivery.Channel.WHATSAPP,
            ):
                for valid_del_status in (
                    ReportDelivery.Status.PENDING,
                    ReportDelivery.Status.SENT,
                    ReportDelivery.Status.FAILED,
                    ReportDelivery.Status.BOUNCED,
                    ReportDelivery.Status.OPENED,
                ):
                    rd = ReportDeliveryFactory(
                        report=rep,
                        channel=valid_channel,
                        status=valid_del_status,
                        whatsapp_url=(
                            "https://wa.me/923001234567"
                            if valid_channel == ReportDelivery.Channel.WHATSAPP
                            else None
                        ),
                    )
                    assert rd.channel == valid_channel
                    assert rd.status == valid_del_status

            # Invalid delivery channel fails at DB -> chk_report_delivery_channel
            with pytest.raises(IntegrityError), transaction.atomic():
                ReportDelivery.objects.create(
                    report=rep,
                    channel="sms_invalid",
                    status=ReportDelivery.Status.PENDING,
                )

            # Invalid delivery status fails at DB -> chk_report_delivery_status
            with pytest.raises(IntegrityError), transaction.atomic():
                ReportDelivery.objects.create(
                    report=rep,
                    channel=ReportDelivery.Channel.EMAIL,
                    status="DELIVERED_INVALID",
                )

    def test_report_version_constraints_and_uniqueness(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            rep = ReportFactory()
            v1 = ReportVersionFactory(
                report=rep,
                version=1,
                pdf_key=f"reports/{rep.id}/1.pdf",
            )
            assert v1.version == 1

            # Duplicate (report_id, version) fails at DB
            # -> uq_report_version_report_id_version
            with pytest.raises(IntegrityError), transaction.atomic():
                ReportVersion.objects.create(
                    report=rep,
                    version=1,
                    pdf_key=f"reports/{rep.id}/1-dup.pdf",
                )

            # Duplicate pdf_key fails at DB -> uq_report_version_pdf_key
            with pytest.raises(IntegrityError), transaction.atomic():
                ReportVersion.objects.create(
                    report=rep,
                    version=2,
                    pdf_key=f"reports/{rep.id}/1.pdf",
                )

            # version <= 0 fails at DB -> chk_report_version_version_pos
            with pytest.raises(IntegrityError), transaction.atomic():
                ReportVersion.objects.create(
                    report=rep,
                    version=0,
                    pdf_key=f"reports/{rep.id}/0.pdf",
                )

    def test_report_access_token_constraints_and_fks_protect(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            sample = SampleFactory()
            staff = StaffUserFactory()
            rep = ReportFactory(sample=sample)
            rv = ReportVersionFactory(report=rep, version=1, generated_by=staff)
            ReportDeliveryFactory(report=rep)
            token = ReportAccessTokenFactory(
                report=rep,
                token_hash="$argon2id$v=19$m=65536,t=3,p=4$fixed$hash001",
            )
            assert rv.report_id == rep.id
            assert token.report_id == rep.id

            # Duplicate token_hash fails at DB
            # -> uq_report_access_token_token_hash
            with pytest.raises(IntegrityError), transaction.atomic():
                ReportAccessTokenFactory(
                    report=rep,
                    token_hash=("$argon2id$v=19$m=65536,t=3,p=4$fixed$hash001"),
                )

            # expires_at <= created_at fails at DB
            # -> chk_report_access_token_expires_after_created
            now = timezone.now()
            with pytest.raises(IntegrityError), transaction.atomic():
                ReportAccessToken.objects.create(
                    report=rep,
                    token_hash=("$argon2id$v=19$m=65536,t=3,p=4$fixed$hash002"),
                    created_at=now,
                    expires_at=now - timedelta(seconds=1),
                )

            with pytest.raises(ProtectedError):
                sample.delete()
            with pytest.raises(ProtectedError):
                staff.delete()
            with pytest.raises(ProtectedError):
                rep.delete()
