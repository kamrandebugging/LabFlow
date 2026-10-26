from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.samples.models import Sample, SampleTest, SampleTransfer
from tests.factories.accounts import StaffUserFactory
from tests.factories.billing import InvoiceFactory, InvoiceItemFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.samples import (
    SampleEventFactory,
    SampleFactory,
    SampleTestFactory,
    SampleTransferFactory,
)


@pytest.mark.django_db
class TestSampleModelsSchemaAndConstraints:
    def test_sample_tables_columns_and_indexes_exist(self, tenant_a: Any) -> None:
        expected_indexes = {
            "sample": {
                "uq_sample_accession_id",
                "idx_sample_invoice_id",
                "idx_sample_branch_id",
                "idx_sample_collected_by",
                "idx_sample_branch_id_status",
            },
            "sample_test": {
                "uq_sample_test_sample_id_test_id",
                "idx_sample_test_sample_id",
                "idx_sample_test_invoice_item_id",
                "idx_sample_test_test_id",
            },
            "sample_event": {
                "idx_sample_event_sample_id",
                "idx_sample_event_actor_id",
                "idx_sample_event_branch_id",
            },
            "sample_transfer": {
                "idx_sample_transfer_sample_id",
                "idx_sample_transfer_from_branch_id",
                "idx_sample_transfer_to_branch_id",
                "idx_sample_transfer_transferred_by",
                "idx_sample_transfer_received_by",
            },
        }
        with tenant_context(tenant_a), connection.cursor() as cursor:
            for table_name, idx_set in expected_indexes.items():
                cursor.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = %s AND tablename = %s;
                    """,
                    [tenant_a.schema_name, table_name],
                )
                present = {r[0] for r in cursor.fetchall()}
                for expected_idx in idx_set:
                    assert expected_idx in present, (
                        f"Missing index {expected_idx} on {table_name}"
                    )

            # Check A-2 columns on sample
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'sample';
                """,
                [tenant_a.schema_name],
            )
            sample_cols = {r[0] for r in cursor.fetchall()}
            assert "rejection_reason_code" in sample_cols
            assert "rejection_note" in sample_cols
            assert "deleted_at" not in sample_cols

            # Check created_at-only shape on sample_test and sample_event
            for tbl in ("sample_test", "sample_event"):
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s;
                    """,
                    [tenant_a.schema_name, tbl],
                )
                cols = {r[0] for r in cursor.fetchall()}
                assert "created_at" in cols
                assert "updated_at" not in cols
                assert "deleted_at" not in cols

            # Check A-9 columns on sample_transfer
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'sample_transfer';
                """,
                [tenant_a.schema_name],
            )
            transfer_cols = {r[0] for r in cursor.fetchall()}
            assert "status" in transfer_cols
            assert "dispatched_at" in transfer_cols
            assert "received_at" in transfer_cols
            assert "deleted_at" not in transfer_cols

    def test_sample_status_check_and_accession_uniqueness(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        with tenant_context(tenant_a):
            inv = InvoiceFactory()
            branch = BranchFactory()
            now = timezone.now()

            for valid_status in (
                Sample.Status.COLLECTED,
                Sample.Status.RECEIVED,
                Sample.Status.IN_PROCESS,
                Sample.Status.READY,
                Sample.Status.REJECTED,
                Sample.Status.CANCELLED,
            ):
                s = SampleFactory(
                    invoice=inv,
                    branch=branch,
                    status=valid_status,
                )
                assert s.status == valid_status

            # Invalid status rejected by chk_sample_status
            with pytest.raises(IntegrityError), transaction.atomic():
                Sample.objects.create(
                    invoice=inv,
                    branch=branch,
                    accession_id="CIT20261020999999",
                    status="disposed_invalid",
                    collected_at=now,
                )

            # Duplicate accession_id in same tenant rejected by uq_sample_accession_id
            SampleFactory(accession_id="CIT20261020888888")
            with pytest.raises(IntegrityError), transaction.atomic():
                SampleFactory(accession_id="CIT20261020888888")

        # Same accession_id in tenant_b succeeds (schema isolation)
        with tenant_context(tenant_b):
            sb = SampleFactory(accession_id="CIT20261020888888")
            assert sb.accession_id == "CIT20261020888888"

    def test_sample_test_unique_per_sample_and_test(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            sample = SampleFactory()
            item = InvoiceItemFactory(invoice=sample.invoice)
            test_obj = TestFactory()

            st = SampleTestFactory(
                sample=sample,
                invoice_item=item,
                test=test_obj,
            )
            assert st.sample_id == sample.id

            # Duplicate (sample_id, test_id) rejected by
            # uq_sample_test_sample_id_test_id
            with pytest.raises(IntegrityError), transaction.atomic():
                SampleTest.objects.create(
                    sample=sample,
                    invoice_item=item,
                    test=test_obj,
                )

    def test_sample_transfer_a9_statuses_and_fks_protect(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            branch_from = BranchFactory()
            branch_to = BranchFactory()
            staff = StaffUserFactory(branch=branch_from)
            inv = InvoiceFactory(branch=branch_from)
            test_obj = TestFactory()
            item = InvoiceItemFactory(invoice=inv, test=test_obj)
            sample = SampleFactory(
                invoice=inv,
                branch=branch_from,
                collected_by=staff,
            )
            SampleTestFactory(sample=sample, invoice_item=item, test=test_obj)
            SampleEventFactory(sample=sample, actor=staff, branch=branch_from)

            for transfer_status in (
                SampleTransfer.Status.OPEN,
                SampleTransfer.Status.RECEIVED,
                SampleTransfer.Status.CANCELLED,
                SampleTransfer.Status.LOST,
            ):
                tr = SampleTransferFactory(
                    sample=sample,
                    from_branch=branch_from,
                    to_branch=branch_to,
                    transferred_by=staff,
                    status=transfer_status,
                )
                assert tr.status == transfer_status

            # Verify PROTECT on all referenced clinical & custody facts
            with pytest.raises(ProtectedError):
                branch_from.delete()
            with pytest.raises(ProtectedError):
                branch_to.delete()
            with pytest.raises(ProtectedError):
                staff.delete()
            with pytest.raises(ProtectedError):
                inv.delete()
            with pytest.raises(ProtectedError):
                item.delete()
            with pytest.raises(ProtectedError):
                test_obj.delete()
            with pytest.raises(ProtectedError):
                sample.delete()
