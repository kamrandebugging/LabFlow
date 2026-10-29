import json
import logging
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from django.conf import settings
from django.db import DatabaseError, connection
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import PasswordResetToken, Role, StaffUser
from apps.branches.models import Branch
from apps.catalog.models import Panel, PanelTest, ReferenceRange, Test, TestPrice
from apps.core.models import Domain, Subscription, Tenant
from apps.core.tenant_settings import TenantSetting
from apps.notifications.models import NotificationTemplate
from apps.partners.models import (
    RevenueShareRule,
)
from apps.platform.provisioning import (
    PROVISIONING_STEPS,
    STEP_HANDLERS,
    TENANT_APPEND_ONLY_TABLES,
    ProvisioningStateSnapshot,
    ProvisionTenantInput,
    cleanup_abandoned_provisioning,
    create_tenant_provisioning,
    get_provisioning_state,
)
from apps.platform.tasks import provision_tenant_task
from tests.factories import (
    AuditLogFactory,
    CriticalNotificationFactory,
    PaymentFactory,
    PlanFactory,
    PlatformUserFactory,
    ReportVersionFactory,
    SampleEventFactory,
    ShareLedgerEntryFactory,
    StaffUserFactory,
)

ALL_LAB6_7_8_TABLES: tuple[str, ...] = (
    # LAB-6 (7 tables)
    "branch",
    "staff_user",
    "staff_branch",
    "login_event",
    "password_reset_token",
    "tenant_setting",
    "audit_log",
    # LAB-7 (22 tables)
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
    # LAB-8 (8 tables)
    "referral_partner",
    "revenue_share_rule",
    "share_ledger_entry",
    "settlement",
    "settlement_line",
    "notification_template",
    "notification",
    "webhook_delivery",
)


def _schema_exists(schema_name: str) -> bool:
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        return cursor.fetchone() is not None


def _drop_schema_if_exists(schema_name: str) -> None:
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


def _platform_jwt(user: Any) -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    return str(
        jwt.encode(
            {"sub": str(user.id), "role": "super_admin", "typ": "access"},
            str(signing_key),
            algorithm="HS256",
        )
    )


def _tenant_staff_jwt(staff_id: Any, tenant_slug: str = "tenant_a") -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    return str(
        jwt.encode(
            {
                "sub": str(staff_id),
                "tenant": tenant_slug,
                "role": "owner",
                "typ": "access",
            },
            str(signing_key),
            algorithm="HS256",
        )
    )


@pytest.mark.django_db(transaction=True)
class TestLab9DefinitionOfDoneVerification:
    """
    Subtask 8 — Verify: Explicit pass/fail checks for LAB-9 / KAN-53 Definition of Done.
    """

    def test_verify_check_1_correct_case_end_to_end_g4(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        Check 1: Correct case (end-to-end, G4)
        POST /platform/tenants with valid input -> tenant, domain, subscription
        in public; when task finishes: tenant schema exists with all LAB-6/7/8
        tables, seed counts match Doc 02 §16, Owner exists with 1 activation token
        (hashed only), status is active, logged total duration <= 3 minutes.
        """
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(sa)}")

        slug = "e2eg4lab"
        schema_name = f"tenant_{slug}"
        owner_email = "owner@e2eg4lab.pk"

        try:
            caplog.set_level(logging.INFO, logger="labflow.provisioning")
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = client.post(
                    "/platform/tenants",
                    {
                        "name": "E2E G4 Lab",
                        "slug": slug,
                        "plan_id": str(plan.id),
                        "owner": {
                            "email": owner_email,
                            "name": "Dr. E2E",
                        },
                    },
                    format="json",
                    HTTP_HOST="localhost",
                )
            assert res.status_code == 202

            # Rows exist in public schema with status 'provisioning'
            tenant = Tenant.objects.get(slug=slug)
            assert tenant.status == "provisioning"
            assert Domain.objects.filter(tenant=tenant, is_primary=True).exists()
            assert Subscription.objects.filter(tenant=tenant, plan=plan).exists()

            # Execute task
            task_res = provision_tenant_task(slug)
            assert task_res["status"] == "active"
            tenant.refresh_from_db()
            assert tenant.status == "active"

            # Tenant schema exists
            assert _schema_exists(schema_name) is True

            # All LAB-6, LAB-7, LAB-8 tables exist in the schema
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = ANY(%s);
                    """,
                    [schema_name, list(ALL_LAB6_7_8_TABLES)],
                )
                found_tables = {row[0] for row in cursor.fetchall()}
                assert set(ALL_LAB6_7_8_TABLES).issubset(found_tables)

            # Seed counts match Doc 02 §16 exactly
            with schema_context(schema_name):
                assert Branch.objects.count() == 1
                assert Panel.objects.count() == 4
                assert PanelTest.objects.count() == 32
                assert Test.objects.count() == 37
                assert TestPrice.objects.count() == 9  # 4 panels + 5 standalone
                # 37 M + 37 F + 27 B (unisex)
                assert ReferenceRange.objects.count() == 101
                assert (
                    NotificationTemplate.objects.count() == 16
                )  # 4 keys * 2 loc * 2 ch
                assert TenantSetting.objects.count() == 6
                assert RevenueShareRule.objects.count() == 0

                # Owner exists with exactly one activation token record
                assert StaffUser.objects.count() == 1
                owner = StaffUser.objects.get(email=owner_email)
                assert owner.role == Role.OWNER
                assert owner.branch is None
                assert owner.is_active is False
                assert owner.password_hash.startswith("!")

                tokens = PasswordResetToken.objects.filter(staff_user=owner)
                assert tokens.count() == 1
                tok = tokens.first()
                assert tok is not None
                assert tok.purpose == PasswordResetToken.Purpose.ACTIVATION
                assert tok.used_at is None
                # Stored hashed only, never plain text
                assert tok.token_hash != ""

            # G4 Performance: Logged total duration <= 3 minutes (180,000 ms)
            p9_logs = [
                json.loads(record.message)
                for record in caplog.records
                if record.name == "labflow.provisioning"
                and '"step": "P-9"' in record.message
            ]
            assert len(p9_logs) == 1
            total_duration_ms = p9_logs[0]["total_duration_ms"]
            assert total_duration_ms <= 180000.0  # <= 3 minutes target

        finally:
            _drop_schema_if_exists(schema_name)

    def test_verify_check_2_correct_case_one_transaction_rollback(self) -> None:
        """
        Check 2: Correct case (one transaction)
        Force failure inside P-2's insert set -> no tenant, domain, or subscription
        row from that attempt remains in public schema.
        """
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(sa)}")

        slug = "p2rollbacklab"
        with (
            patch(
                "apps.platform.provisioning.Subscription.objects.create",
                side_effect=RuntimeError("Forced P-2 mid-insert crash"),
            ),
            patch(
                "apps.platform.provisioning.provision_tenant_task.delay"
            ) as mock_delay,
            pytest.raises(RuntimeError, match="Forced P-2 mid-insert crash"),
        ):
            client.post(
                "/platform/tenants",
                {
                    "name": "P2 Rollback Lab",
                    "slug": slug,
                    "plan_id": str(plan.id),
                    "owner": {
                        "email": "owner@rollback.pk",
                        "name": "Dr. Rollback",
                    },
                },
                format="json",
                HTTP_HOST="localhost",
            )

        # Zero rows from that attempt remain
        assert Tenant.objects.filter(slug=slug).exists() is False
        assert Domain.objects.filter(domain__startswith=f"{slug}.").exists() is False
        assert Subscription.objects.filter(tenant__slug=slug).exists() is False
        mock_delay.assert_not_called()

    def test_verify_check_3_idempotency_double_submit(self) -> None:
        """
        Check 3: Idempotency case (double submit)
        Submit same create request twice with same slug -> exactly 1 tenant row;
        second request is rejected as conflict and does not enqueue a 2nd run.
        """
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(sa)}")

        slug = "doublesubmitlab"
        payload = {
            "name": "Double Submit Lab",
            "slug": slug,
            "plan_id": str(plan.id),
            "owner": {
                "email": "owner@doublesubmit.pk",
                "name": "Dr. Double",
            },
        }

        with patch(
            "apps.platform.provisioning.provision_tenant_task.delay"
        ) as mock_delay:
            res1 = client.post(
                "/platform/tenants", payload, format="json", HTTP_HOST="localhost"
            )
            assert res1.status_code == 202
            assert mock_delay.call_count == 1

            # Second submit without idempotency key -> 409 conflict
            res2 = client.post(
                "/platform/tenants", payload, format="json", HTTP_HOST="localhost"
            )
            assert res2.status_code == 409
            assert res2.json()["code"] == "slug_taken"
            # Does not enqueue a second provisioning run
            assert mock_delay.call_count == 1

        assert Tenant.objects.filter(slug=slug).count() == 1

    def test_verify_check_4_idempotency_task_rerun(self) -> None:
        """
        Check 4: Idempotency case (task re-run)
        Invoke provisioning task again for now-active tenant -> seed counts unchanged,
        still exactly one Owner and one live activation token, no 0% rule, stays active.
        """
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "rerunactivelab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Rerun Active Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@rerunactive.pk",
                        owner_name="Dr. Rerun",
                        actor_id=sa.id,
                    )
                )

            # First run completes
            run1 = provision_tenant_task(slug)
            assert run1["status"] == "active"

            with schema_context(schema_name):
                initial_counts = (
                    Branch.objects.count(),
                    Panel.objects.count(),
                    Test.objects.count(),
                    PanelTest.objects.count(),
                    TestPrice.objects.count(),
                    ReferenceRange.objects.count(),
                    NotificationTemplate.objects.count(),
                    TenantSetting.objects.count(),
                )

            # Second run on active tenant -> resumed no-op
            run2 = provision_tenant_task(slug)
            assert run2["status"] == "active"
            assert run2["resumed_noop"] is True

            with schema_context(schema_name):
                after_counts = (
                    Branch.objects.count(),
                    Panel.objects.count(),
                    Test.objects.count(),
                    PanelTest.objects.count(),
                    TestPrice.objects.count(),
                    ReferenceRange.objects.count(),
                    NotificationTemplate.objects.count(),
                    TenantSetting.objects.count(),
                )
                assert after_counts == initial_counts
                assert StaffUser.objects.count() == 1
                owner = StaffUser.objects.get(email="owner@rerunactive.pk")
                assert (
                    PasswordResetToken.objects.filter(
                        staff_user=owner,
                        purpose=PasswordResetToken.Purpose.ACTIVATION,
                        used_at__isnull=True,
                    ).count()
                    == 1
                )
                assert RevenueShareRule.objects.count() == 0

            res.tenant.refresh_from_db()
            assert res.tenant.status == "active"
        finally:
            _drop_schema_if_exists(schema_name)

    def test_verify_check_5_resume_case_tp3(self) -> None:
        """
        Check 5: Resume case (TP-3)
        Kill worker mid-seed (P-6) on fresh tenant -> status remains provisioning and
        failed step recorded; retry task -> resumes, completes, passes with no dupes.
        """
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "midseedcrashedlab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Mid Seed Crashed Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@midseed.pk",
                        owner_name="Dr. MidSeed",
                        actor_id=sa.id,
                    )
                )

            def _crash_p6(_t: Tenant, _st: ProvisioningStateSnapshot) -> None:
                raise RuntimeError("Worker killed mid-seed at P-6")

            with (
                patch.dict(STEP_HANDLERS, {"P-6": _crash_p6}),
                pytest.raises(RuntimeError, match="Worker killed mid-seed at P-6"),
            ):
                provision_tenant_task(slug)

            # Tenant status remains provisioning; failed step recorded by name
            res.tenant.refresh_from_db()
            assert res.tenant.status == "provisioning"
            state_after_crash = get_provisioning_state(res.tenant)
            assert state_after_crash.failed_step == "P-6"
            assert "Worker killed mid-seed at P-6" in str(state_after_crash.error)

            # Retry the task without failure -> resumes and completes
            retry_res = provision_tenant_task(slug)
            assert retry_res["status"] == "active"
            res.tenant.refresh_from_db()
            assert res.tenant.status == "active"

            # Final state has no duplicate seeds
            with schema_context(schema_name):
                assert Branch.objects.count() == 1
                assert Panel.objects.count() == 4
                assert Test.objects.count() == 37
                assert PanelTest.objects.count() == 32
                assert NotificationTemplate.objects.count() == 16
                assert RevenueShareRule.objects.count() == 0
                assert StaffUser.objects.count() == 1
        finally:
            _drop_schema_if_exists(schema_name)

    def test_verify_check_6_security_case_auth_and_append_only(
        self, tenant_a: Tenant
    ) -> None:
        """
        Check 6: Security case
        Unauthenticated POST /platform/tenants -> 401;
        carrying tenant staff credentials -> 401;
        in new tenant schema, app role cannot UPDATE/DELETE append-only tables.
        """
        client = APIClient()
        plan = PlanFactory(is_active=True)
        payload = {
            "name": "Sec Lab",
            "slug": "seclab",
            "plan_id": str(plan.id),
            "owner": {"email": "owner@sec.pk", "name": "Dr. Sec"},
        }

        # 1. Unauthenticated -> 401
        res_unauth = client.post(
            "/platform/tenants", payload, format="json", HTTP_HOST="localhost"
        )
        assert res_unauth.status_code == 401

        # 2. Tenant staff credentials -> 401
        with schema_context(tenant_a.schema_name):
            staff = StaffUserFactory(role="owner")
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_tenant_staff_jwt(staff.id, tenant_a.slug)}"
        )
        res_staff = client.post(
            "/platform/tenants", payload, format="json", HTTP_HOST="localhost"
        )
        assert res_staff.status_code == 401

        # 3. New tenant schema: app role blocked from UPDATE/DELETE on append-only
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        slug = "secp5checklab"
        schema_name = f"tenant_{slug}"
        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Sec P5 Check Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@secp5.pk",
                        owner_name="Dr. SecP5",
                        actor_id=sa.id,
                    )
                )
            provision_tenant_task(slug)

            with schema_context(schema_name):
                audit_row = AuditLogFactory(action="test.verify")
                payment_row = PaymentFactory(amount=Decimal("500.00"))
                sample_event_row = SampleEventFactory(event="COLLECTED")
                report_version_row = ReportVersionFactory(version=1)
                crit_notif_row = CriticalNotificationFactory(notified_name="Dr. Sec")
                ledger_row = ShareLedgerEntryFactory(amount=Decimal("100.00"))

                targets = [
                    ("audit_log", "action", audit_row.id),
                    ("payment", "reference", payment_row.id),
                    ("sample_event", "note", sample_event_row.id),
                    ("report_version", "pdf_key", report_version_row.id),
                    ("critical_notification", "notified_name", crit_notif_row.id),
                    ("share_ledger_entry", "period", ledger_row.id),
                ]
                assert {t[0] for t in targets} == set(TENANT_APPEND_ONLY_TABLES)

                for table_name, field_name, row_id in targets:
                    with pytest.raises(DatabaseError), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{schema_name}"."{table_name}" '
                            f'SET "{field_name}" = %s WHERE id = %s',
                            ["tampered", str(row_id)],
                        )
                    with pytest.raises(DatabaseError), connection.cursor() as cursor:
                        cursor.execute(
                            f'DELETE FROM "{schema_name}"."{table_name}" WHERE id = %s',
                            [str(row_id)],
                        )
        finally:
            _drop_schema_if_exists(schema_name)

    def test_verify_check_7_cleanup_case_dod(self) -> None:
        """
        Check 7: Cleanup case (DoD)
        Run abandoned-provisioning cleanup on tenant stuck in provisioning ->
        schema no longer exists (pg_namespace has no such schema) and tenant record
        disposed as Doc 04 §5 specifies (status='deleted').
        """
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "dodabandonedlab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="DoD Abandoned Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@dodabandoned.pk",
                        owner_name="Dr. Abandoned",
                        actor_id=sa.id,
                    )
                )

            def _halt_p4(_t: Tenant, _st: ProvisioningStateSnapshot) -> None:
                raise RuntimeError("Halted at P-4")

            with (
                patch.dict(STEP_HANDLERS, {"P-4": _halt_p4}),
                pytest.raises(RuntimeError, match="Halted at P-4"),
            ):
                provision_tenant_task(slug)

            assert _schema_exists(schema_name) is True

            # Run cleanup
            cleaned = cleanup_abandoned_provisioning(slug, actor_id=sa.id)
            assert cleaned.status == "deleted"

            # Schema no longer exists in pg_namespace
            assert _schema_exists(schema_name) is False

            # Tenant record marked deleted
            assert Tenant.objects.filter(slug=slug, status="deleted").exists() is True
            assert Domain.objects.filter(tenant=res.tenant).exists() is False
        finally:
            _drop_schema_if_exists(schema_name)

    def test_verify_check_8_performance_case_per_step_durations_and_slug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        Check 8: Performance case
        <= 3-minute total from end-to-end check, with per-step durations present in logs
        for every step, each line carrying tenant_slug.
        """
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "perfchecklab"
        schema_name = f"tenant_{slug}"

        try:
            caplog.set_level(logging.INFO, logger="labflow.provisioning")
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Perf Check Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@perfcheck.pk",
                        owner_name="Dr. Perf",
                        actor_id=sa.id,
                    )
                )

            task_res = provision_tenant_task(slug)
            assert task_res["status"] == "active"

            # Extract structured logs from provisioning runner
            logs = [
                json.loads(record.message)
                for record in caplog.records
                if record.name == "labflow.provisioning"
                and '"event": "provisioning_step"' in record.message
            ]

            assert len(logs) == len(PROVISIONING_STEPS)
            for idx, step_code in enumerate(PROVISIONING_STEPS):
                entry = logs[idx]
                assert entry["tenant_slug"] == slug
                assert entry["step"] == step_code
                assert entry["outcome"] == "completed"
                assert isinstance(entry["duration_ms"], (int, float))
                assert entry["duration_ms"] >= 0.0

            # Final step has total_duration_ms <= 3 minutes (180,000 ms)
            p9_entry = logs[-1]
            assert p9_entry["step"] == "P-9"
            assert "total_duration_ms" in p9_entry
            assert p9_entry["total_duration_ms"] <= 180000.0

        finally:
            _drop_schema_if_exists(schema_name)
