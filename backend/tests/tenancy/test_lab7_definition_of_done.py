from decimal import Decimal
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, tenant_context

from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.catalog.models import (
    Panel,
    PanelTest,
    ReferenceRange,
    Test,
    TestPrice,
)
from apps.patients.models import Patient, PatientConsent, PatientContact
from apps.reports.models import (
    Report,
    ReportAccessToken,
    ReportDelivery,
    ReportVersion,
)
from apps.results.models import CriticalNotification, Result, ResultApproval
from apps.samples.models import Sample, SampleEvent, SampleTest, SampleTransfer
from tests.factories.accounts import StaffUserFactory
from tests.factories.billing import (
    InvoiceFactory,
    InvoiceItemFactory,
    PaymentFactory,
)
from tests.factories.catalog import PanelFactory, TestFactory, TestPriceFactory
from tests.factories.reports import ReportVersionFactory
from tests.factories.results import CriticalNotificationFactory
from tests.factories.samples import SampleEventFactory, SampleFactory
from tests.isolation.generator import get_tenant_models

LAB7_22_TABLES: tuple[str, ...] = (
    "patient",
    "patient_contact",
    "patient_consent",
    "test",
    "panel",
    "panel_test",
    "test_price",
    "reference_range",
    "invoice",
    "invoice_item",
    "payment",
    "sample",
    "sample_test",
    "sample_event",
    "sample_transfer",
    "result",
    "result_approval",
    "critical_notification",
    "report",
    "report_version",
    "report_delivery",
    "report_access_token",
)

LAB7_22_MODELS: tuple[type, ...] = (
    Patient,
    PatientContact,
    PatientConsent,
    Test,
    Panel,
    PanelTest,
    TestPrice,
    ReferenceRange,
    Invoice,
    InvoiceItem,
    Payment,
    Sample,
    SampleTest,
    SampleEvent,
    SampleTransfer,
    Result,
    ResultApproval,
    CriticalNotification,
    Report,
    ReportVersion,
    ReportDelivery,
    ReportAccessToken,
)

LAB7_APPEND_ONLY_TABLES: tuple[str, ...] = (
    "payment",
    "sample_event",
    "report_version",
    "critical_notification",
)


@pytest.mark.django_db
class TestLab7DefinitionOfDone:
    def test_check1_placement_drift_and_extensions(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        """
        Check 1 — Correct case (placement + drift):
        All 22 LAB-7 tables exist in tenant schemas and none in public schema;
        makemigrations --check --dry-run exits 0 with 'No changes detected';
        pg_extension shows pg_trgm present and pgcrypto absent.
        """
        public_schema = get_public_schema_name()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE';
                """,
                [public_schema],
            )
            public_tables = {r[0] for r in cursor.fetchall()}
            for tbl in LAB7_22_TABLES:
                assert tbl not in public_tables, (
                    f"Tenant table {tbl} leaked into public schema!"
                )

            for tenant in (tenant_a, tenant_b):
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_type = 'BASE TABLE';
                    """,
                    [tenant.schema_name],
                )
                tenant_tables = {r[0] for r in cursor.fetchall()}
                for tbl in LAB7_22_TABLES:
                    assert tbl in tenant_tables, (
                        f"Missing LAB-7 table {tbl} in {tenant.schema_name}"
                    )

            cursor.execute("SELECT extname FROM pg_extension;")
            extensions = {r[0] for r in cursor.fetchall()}
            assert "pg_trgm" in extensions
            assert "pgcrypto" not in extensions

        out = StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=out)
        assert "No changes detected" in out.getvalue()

    def test_check2_xor_checks_on_test_price_and_invoice_item(
        self, tenant_a: Any
    ) -> None:
        """
        Check 2 — Error case (XOR CHECKs):
        test_price and invoice_item with both parents set -> check violation;
        with neither set -> check violation; with exactly one -> inserts.
        """
        with tenant_context(tenant_a):
            test_obj = TestFactory()
            panel_obj = PanelFactory()
            now = timezone.now()

            # test_price: both set -> fails chk_test_price_test_xor_panel
            with (
                pytest.raises(IntegrityError) as exc_tp_both,
                transaction.atomic(),
            ):
                TestPrice.objects.create(
                    test=test_obj,
                    panel=panel_obj,
                    price=Decimal("500.00"),
                    effective_from=now,
                )
            assert "chk_test_price_test_xor_panel" in str(exc_tp_both.value)

            # test_price: neither set -> fails chk_test_price_test_xor_panel
            with (
                pytest.raises(IntegrityError) as exc_tp_none,
                transaction.atomic(),
            ):
                TestPrice.objects.create(
                    test=None,
                    panel=None,
                    price=Decimal("500.00"),
                    effective_from=now,
                )
            assert "chk_test_price_test_xor_panel" in str(exc_tp_none.value)

            # test_price: exactly one -> inserts
            tp1 = TestPrice.objects.create(
                test=test_obj,
                panel=None,
                price=Decimal("500.00"),
                effective_from=now,
            )
            tp2 = TestPrice.objects.create(
                test=None,
                panel=panel_obj,
                price=Decimal("1200.00"),
                effective_from=now,
            )
            assert tp1.pk is not None and tp2.pk is not None

            inv = InvoiceFactory()

            # invoice_item: both set -> fails chk_invoice_item_test_xor_panel
            with (
                pytest.raises(IntegrityError) as exc_ii_both,
                transaction.atomic(),
            ):
                InvoiceItem.objects.create(
                    invoice=inv,
                    test=test_obj,
                    panel=panel_obj,
                    description="Both set",
                    unit_price=Decimal("500.00"),
                    quantity=1,
                    line_total=Decimal("500.00"),
                )
            assert "chk_invoice_item_test_xor_panel" in str(exc_ii_both.value)

            # invoice_item: neither set -> fails chk_invoice_item_test_xor_panel
            with (
                pytest.raises(IntegrityError) as exc_ii_none,
                transaction.atomic(),
            ):
                InvoiceItem.objects.create(
                    invoice=inv,
                    test=None,
                    panel=None,
                    description="Neither set",
                    unit_price=Decimal("500.00"),
                    quantity=1,
                    line_total=Decimal("500.00"),
                )
            assert "chk_invoice_item_test_xor_panel" in str(exc_ii_none.value)

            # invoice_item: exactly one -> inserts
            ii1 = InvoiceItem.objects.create(
                invoice=inv,
                test=test_obj,
                panel=None,
                description="Test only",
                unit_price=Decimal("500.00"),
                quantity=1,
                line_total=Decimal("500.00"),
            )
            ii2 = InvoiceItem.objects.create(
                invoice=inv,
                test=None,
                panel=panel_obj,
                description="Panel only",
                unit_price=Decimal("1200.00"),
                quantity=1,
                line_total=Decimal("1200.00"),
            )
            assert ii1.pk is not None and ii2.pk is not None

    def test_check3_financial_idempotency_partial_unique(self, tenant_a: Any) -> None:
        """
        Check 3 — Idempotency case (financial):
        Two invoice rows with the same idempotency_key fail with IntegrityError
        naming uq_invoice_idempotency_key.
        """
        with tenant_context(tenant_a):
            InvoiceFactory(idempotency_key="dod-inv-idem-001")
            with (
                pytest.raises(IntegrityError) as exc_info,
                transaction.atomic(),
            ):
                InvoiceFactory(idempotency_key="dod-inv-idem-001")
            assert "uq_invoice_idempotency_key" in str(exc_info.value)

    def test_check4_checks_on_named_columns_and_result_withdrawn_and_null_flag(
        self, tenant_a: Any
    ) -> None:
        """
        Check 4 — Error case (CHECKs on named columns):
        payment invalid kind -> chk_payment_kind;
        payment invalid method -> chk_payment_method;
        result invalid status -> chk_result_status;
        result status='withdrawn' inserts fine;
        result flag=NULL inserts fine.
        """
        with tenant_context(tenant_a):
            inv = InvoiceFactory()

            with (
                pytest.raises(IntegrityError) as exc_kind,
                transaction.atomic(),
            ):
                Payment.objects.create(
                    invoice=inv,
                    kind="invalid_kind",
                    method=Payment.Method.CASH,
                    amount=Decimal("100.00"),
                )
            assert "chk_payment_kind" in str(exc_kind.value)

            with (
                pytest.raises(IntegrityError) as exc_method,
                transaction.atomic(),
            ):
                Payment.objects.create(
                    invoice=inv,
                    kind=Payment.Kind.PAYMENT,
                    method="invalid_method",
                    amount=Decimal("100.00"),
                )
            assert "chk_payment_method" in str(exc_method.value)

            sample = SampleFactory(invoice=inv)
            test_obj = TestFactory()
            staff = StaffUserFactory()

            with (
                pytest.raises(IntegrityError) as exc_res_status,
                transaction.atomic(),
            ):
                Result.objects.create(
                    sample=sample,
                    test=test_obj,
                    value="5.5",
                    status="invalid_result_status",
                    entered_by=staff,
                )
            assert "chk_result_status" in str(exc_res_status.value)

            res_withdrawn_null_flag = Result.objects.create(
                sample=sample,
                test=test_obj,
                value="Positive",
                flag=None,
                status=Result.Status.WITHDRAWN,
                entered_by=staff,
            )
            assert res_withdrawn_null_flag.pk is not None
            assert res_withdrawn_null_flag.status == "withdrawn"
            assert res_withdrawn_null_flag.flag is None

    def test_check5_security_append_only_revoke_enforced(self, tenant_a: Any) -> None:
        """
        Check 5 — Security case (append-only REVOKE):
        SELECT/INSERT succeed on payment, sample_event, report_version,
        critical_notification; UPDATE and DELETE fail with permission denied
        when executed as a non-superuser role with the app role's table grants.
        """
        with tenant_context(tenant_a):
            pay = PaymentFactory()
            sev = SampleEventFactory()
            rv = ReportVersionFactory()
            crit = CriticalNotificationFactory()

            with connection.cursor() as cursor:
                # 1. Verify role_table_grants for current_user
                for tbl in LAB7_APPEND_ONLY_TABLES:
                    cursor.execute(
                        """
                        SELECT privilege_type
                        FROM information_schema.role_table_grants
                        WHERE table_schema = %s
                          AND table_name = %s
                          AND grantee = current_user;
                        """,
                        [tenant_a.schema_name, tbl],
                    )
                    grants = {r[0] for r in cursor.fetchall()}
                    assert "SELECT" in grants
                    assert "INSERT" in grants
                    assert "UPDATE" not in grants
                    assert "DELETE" not in grants
                    assert "TRUNCATE" not in grants

                # 2. Verify runtime permission denied using a non-superuser role
                # mirrored to the exact table grants of current_user (since
                # local/CI test DB user may have rolsuper=true which bypasses
                # table ACLs unless tested via a non-superuser role).
                cursor.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_roles
                            WHERE rolname = 'labflow_dod_app_probe'
                        ) THEN
                            CREATE ROLE labflow_dod_app_probe
                                NOLOGIN NOSUPERUSER NOBYPASSRLS;
                        END IF;
                    END
                    $$;
                    """
                )
                quoted_schema = connection.ops.quote_name(tenant_a.schema_name)
                cursor.execute(
                    f"GRANT USAGE ON SCHEMA {quoted_schema} TO labflow_dod_app_probe;"
                )
                for tbl in LAB7_APPEND_ONLY_TABLES:
                    q_tbl = connection.ops.quote_name(tbl)
                    cursor.execute(
                        f"REVOKE ALL ON TABLE {quoted_schema}.{q_tbl} "
                        f"FROM labflow_dod_app_probe;"
                    )
                    cursor.execute(
                        f"GRANT SELECT, INSERT ON TABLE "
                        f"{quoted_schema}.{q_tbl} TO labflow_dod_app_probe;"
                    )

                for tbl, row_id, update_col, update_val in (
                    ("payment", pay.id, "reference", "'mutated'"),
                    ("sample_event", sev.id, "note", "'mutated'"),
                    ("report_version", rv.id, "pdf_key", "'mutated.pdf'"),
                    (
                        "critical_notification",
                        crit.id,
                        "notified_name",
                        "'mutated'",
                    ),
                ):
                    q_tbl = connection.ops.quote_name(tbl)
                    # SELECT succeeds under probe role
                    with transaction.atomic():
                        cursor.execute("SET LOCAL ROLE labflow_dod_app_probe;")
                        cursor.execute(
                            f"SELECT id FROM {quoted_schema}.{q_tbl} WHERE id = %s;",
                            [row_id],
                        )
                        assert cursor.fetchone() is not None

                    # UPDATE fails with permission denied
                    with (
                        pytest.raises(DatabaseError) as exc_upd,
                        transaction.atomic(),
                    ):
                        cursor.execute("SET LOCAL ROLE labflow_dod_app_probe;")
                        cursor.execute(
                            f"UPDATE {quoted_schema}.{q_tbl} "
                            f"SET {update_col} = {update_val} "
                            f"WHERE id = %s;",
                            [row_id],
                        )
                    assert "permission denied" in str(exc_upd.value).lower()

                    # DELETE fails with permission denied
                    with (
                        pytest.raises(DatabaseError) as exc_del,
                        transaction.atomic(),
                    ):
                        cursor.execute("SET LOCAL ROLE labflow_dod_app_probe;")
                        cursor.execute(
                            f"DELETE FROM {quoted_schema}.{q_tbl} WHERE id = %s;",
                            [row_id],
                        )
                    assert "permission denied" in str(exc_del.value).lower()

    def test_check6_security_token_storage_and_price_snapshot(
        self, tenant_a: Any
    ) -> None:
        """
        Check 6 — Security case (token storage + snapshot rule):
        report_access_token has token_hash and no plain token column;
        updating test_price.price does not alter existing invoice_item.unit_price.
        """
        with tenant_context(tenant_a):
            with connection.cursor() as cursor:
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
                assert "token_hash" in rat_cols
                for forbidden in (
                    "token",
                    "plain_token",
                    "raw_token",
                    "secret",
                ):
                    assert forbidden not in rat_cols

            test_obj = TestFactory(name="TSH")
            tp = TestPriceFactory(
                test=test_obj,
                panel=None,
                price=Decimal("1800.00"),
            )
            inv = InvoiceFactory()
            item = InvoiceItemFactory(
                invoice=inv,
                test=test_obj,
                panel=None,
                description=test_obj.name,
                unit_price=tp.price,
                quantity=1,
                line_total=tp.price,
            )
            tp.price = Decimal("2500.00")
            tp.save()

            item.refresh_from_db()
            assert item.unit_price == Decimal("1800.00")
            assert item.line_total == Decimal("1800.00")

    def test_check7_isolation_generator_covers_all_22_lab7_models(
        self,
    ) -> None:
        """
        Check 7 — Isolation case:
        All 22 LAB-7 models are discovered by the dynamic cross-tenant isolation
        generator with zero exclusions.
        """
        discovered_models = set(get_tenant_models())
        for model_cls in LAB7_22_MODELS:
            assert model_cls in discovered_models, (
                f"LAB-7 model {model_cls._meta.label} missing from isolation generator!"
            )

    def test_check8_performance_trigram_fk_indexes_and_money_precision(
        self, tenant_a: Any
    ) -> None:
        """
        Check 8 — Performance & Money Precision case:
        pg_indexes confirms GIN trigram indexes on patient.name and patient.phone,
        and an index exists on every foreign key across all 22 LAB-7 tables;
        money columns are numeric(12,2) and zero float/double columns exist.
        """
        with tenant_context(tenant_a), connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT tablename, indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = %s;
                    """,
                [tenant_a.schema_name],
            )
            all_indexes = cursor.fetchall()
            by_table: dict[str, dict[str, str]] = {}
            for tbl, idx_name, idx_def in all_indexes:
                by_table.setdefault(tbl, {})[idx_name] = idx_def

            # 1. Trigram GIN indexes on patient name and phone
            patient_indexes = by_table.get("patient", {})
            assert "idx_patient_name_trgm" in patient_indexes
            assert "USING gin" in patient_indexes["idx_patient_name_trgm"]
            assert "gin_trgm_ops" in patient_indexes["idx_patient_name_trgm"]
            assert "idx_patient_phone_trgm" in patient_indexes
            assert "USING gin" in patient_indexes["idx_patient_phone_trgm"]
            assert "gin_trgm_ops" in patient_indexes["idx_patient_phone_trgm"]

            # 2. Every FK column across all 22 LAB-7 models has an index
            for model_cls in LAB7_22_MODELS:
                tbl = model_cls._meta.db_table
                tbl_idx_defs = list(by_table.get(tbl, {}).values())
                for field in model_cls._meta.local_fields:
                    if field.is_relation and field.many_to_one:
                        fk_col = field.column
                        has_leading_or_dedicated_idx = any(
                            f"({fk_col})" in idx_def or f"({fk_col}," in idx_def
                            for idx_def in tbl_idx_defs
                        )
                        assert has_leading_or_dedicated_idx, (
                            f"FK column {tbl}.{fk_col} has no index in pg_indexes!"
                        )

            # 3. Money columns are numeric(12,2) and no float/double columns exist
            money_columns = [
                ("test_price", "price"),
                ("invoice", "subtotal"),
                ("invoice", "discount_amount"),
                ("invoice", "total"),
                ("invoice_item", "unit_price"),
                ("invoice_item", "line_total"),
                ("payment", "amount"),
            ]
            for tbl, col in money_columns:
                cursor.execute(
                    """
                        SELECT data_type, numeric_precision, numeric_scale
                        FROM information_schema.columns
                        WHERE table_schema = %s
                          AND table_name = %s
                          AND column_name = %s;
                        """,
                    [tenant_a.schema_name, tbl, col],
                )
                assert cursor.fetchone() == ("numeric", 12, 2), (
                    f"{tbl}.{col} is not numeric(12,2)!"
                )

            cursor.execute(
                """
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = ANY(%s)
                      AND data_type IN ('real', 'double precision', 'float');
                    """,
                [tenant_a.schema_name, list(LAB7_22_TABLES)],
            )
            float_cols = cursor.fetchall()
            assert float_cols == [], (
                f"Forbidden float columns found in LAB-7 tables: {float_cols}"
            )
