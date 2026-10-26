from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django_tenants.utils import tenant_context

from apps.results.models import Result
from tests.factories.accounts import StaffUserFactory
from tests.factories.catalog import TestFactory
from tests.factories.results import (
    CriticalNotificationFactory,
    ResultApprovalFactory,
    ResultFactory,
)
from tests.factories.samples import SampleFactory


@pytest.mark.django_db
class TestResultModelsSchemaAndConstraints:
    def test_result_tables_columns_and_indexes_exist(self, tenant_a: Any) -> None:
        expected_indexes = {
            "result": {
                "idx_result_sample_id",
                "idx_result_test_id",
                "idx_result_entered_by",
            },
            "result_approval": {
                "idx_result_approval_result_id",
                "idx_result_approval_pathologist_id",
            },
            "critical_notification": {
                "idx_critical_notification_result_id",
                "idx_critical_notification_recorded_by",
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

            # Verify result columns and nullable flag
            cursor.execute(
                """
                    SELECT column_name, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = 'result';
                    """,
                [tenant_a.schema_name],
            )
            result_cols = {r[0]: r[1] for r in cursor.fetchall()}
            assert set(result_cols.keys()) == {
                "id",
                "sample_id",
                "test_id",
                "value",
                "unit",
                "flag",
                "status",
                "entered_by",
                "created_at",
                "updated_at",
            }
            assert result_cols["flag"] == "YES"
            assert result_cols["unit"] == "YES"
            assert result_cols["value"] == "NO"
            assert "deleted_at" not in result_cols

            # Verify result_approval and critical_notification have created_at only
            for tbl in ("result_approval", "critical_notification"):
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

    def test_result_status_check_constraint_and_nullable_flag(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            sample = SampleFactory()
            test_obj = TestFactory()
            staff = StaffUserFactory()

            # All 5 statuses (including withdrawn) and all flags
            # (including NULL) succeed
            for valid_status in (
                Result.Status.ENTERED,
                Result.Status.APPROVED,
                Result.Status.REJECTED,
                Result.Status.AMENDED,
                Result.Status.WITHDRAWN,
            ):
                r = ResultFactory(
                    sample=sample,
                    test=test_obj,
                    entered_by=staff,
                    status=valid_status,
                    flag=None,
                )
                assert r.status == valid_status
                assert r.flag is None

            for valid_flag in (
                Result.Flag.LOW,
                Result.Flag.NORMAL,
                Result.Flag.HIGH,
                Result.Flag.CRITICAL,
            ):
                r_flagged = ResultFactory(
                    sample=sample,
                    test=test_obj,
                    entered_by=staff,
                    flag=valid_flag,
                )
                assert r_flagged.flag == valid_flag

            # Invalid status rejected by chk_result_status at DB level
            with pytest.raises(IntegrityError), transaction.atomic():
                Result.objects.create(
                    sample=sample,
                    test=test_obj,
                    value="10.0",
                    status="pending_invalid",
                    entered_by=staff,
                )

    def test_result_approval_range_override_and_critical_notification_fks_protect(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            sample = SampleFactory()
            test_obj = TestFactory()
            tech = StaffUserFactory()
            pathologist = StaffUserFactory()
            res = ResultFactory(
                sample=sample,
                test=test_obj,
                entered_by=tech,
                flag=Result.Flag.CRITICAL,
                status=Result.Status.APPROVED,
            )
            approval = ResultApprovalFactory(
                result=res,
                pathologist=pathologist,
                range_override=True,
                note="Verified on repeat dilution",
            )
            crit = CriticalNotificationFactory(
                result=res,
                recorded_by=pathologist,
                read_back=True,
            )
            assert approval.range_override is True
            assert crit.read_back is True

            with pytest.raises(ProtectedError):
                sample.delete()
            with pytest.raises(ProtectedError):
                test_obj.delete()
            with pytest.raises(ProtectedError):
                tech.delete()
            with pytest.raises(ProtectedError):
                pathologist.delete()
            with pytest.raises(ProtectedError):
                res.delete()
