import logging
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.db import connection
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import PasswordResetToken, Role, StaffUser
from apps.platform.provisioning import (
    ProvisionTenantInput,
    create_tenant_owner_activation,
    create_tenant_provisioning,
    execute_step_p3_create_schema,
    execute_step_p4_migrate_schema,
    execute_step_p8_create_owner,
    get_provisioning_state,
)
from apps.platform.tasks import provision_tenant_task
from tests.factories import PlanFactory, PlatformUserFactory


def _drop_schema_if_exists(schema_name: str) -> None:
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


@pytest.mark.django_db(transaction=True)
class TestStepP8OwnerCreationAndActivationToken:
    """
    Subtask 6 (Story KAN-53 / Epic LAB-9 — TN-08):
    Create tenant Owner staff_user in tenant schema in not-yet-activated state
    (is_active=False, no usable password, branch=None), with an activation credential
    as password_reset_token (purpose='activation', hashed token, 72h expiry).
    Plain token delivered only via email URL fragment; re-run supersedes live token.
    """

    def test_tn08_p8_creates_owner_in_tenant_schema_inactive_no_branch(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "ownerchecklab"
        schema_name = f"tenant_{slug}"
        owner_email = "owner@ownercheck.pk"
        owner_name = "Dr. Owner"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Owner Check Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email=owner_email,
                        owner_name=owner_name,
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            state = get_provisioning_state(tenant)

            execute_step_p3_create_schema(tenant, state)
            execute_step_p4_migrate_schema(tenant, state)

            mail.outbox.clear()
            execute_step_p8_create_owner(tenant, state)

            with schema_context(schema_name):
                assert StaffUser.objects.count() == 1
                owner = StaffUser.objects.get(email=owner_email)

                # Role is exactly OWNER (Doc 02 §5.1, Doc 04 §5 P-8)
                assert owner.role == Role.OWNER
                # Tenant-wide scope: branch_id is NULL (Doc 04 §5 P-8, Doc 08 §5.2)
                assert owner.branch is None
                # Not yet activated
                assert owner.is_active is False
                # TOTP enrols at first login, not during provisioning (LAB-12)
                assert owner.totp_enabled is False
                # Unusable password set by provisioning; starts with '!' (Doc 04 §5 P-8)
                assert owner.password_hash.startswith("!")
                assert not check_password("random_pass", owner.password_hash)

                # Activation token verification (A-14 revised, Doc 04 §5 P-8)
                tokens = PasswordResetToken.objects.filter(staff_user=owner)
                assert tokens.count() == 1
                token_row = tokens.first()
                assert token_row is not None
                assert token_row.purpose == PasswordResetToken.Purpose.ACTIVATION
                assert token_row.used_at is None
                assert token_row.expires_at > token_row.created_at

                # Expiry matches 72 hours (Doc 04 §5 P-8, Doc 08 §4.5, §4.7)
                delta = token_row.expires_at - token_row.created_at
                assert abs(delta.total_seconds() - 72 * 3600) < 60

            # Plain token delivered via email to tenant subdomain
            assert len(mail.outbox) == 1
            sent_email = mail.outbox[0]
            assert owner_email in sent_email.to
            expected_subject = f"Activate your LabFlow account - {tenant.name}"
            assert expected_subject in sent_email.subject
            assert f"https://{slug}.labflow.app/activate#" in sent_email.body

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn08_token_stored_hashed_only_and_plain_token_verified(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "tokenchecklab"
        schema_name = f"tenant_{slug}"
        owner_email = "owner@tokencheck.pk"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Token Check Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email=owner_email,
                        owner_name="Dr. Token",
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            state = get_provisioning_state(tenant)
            execute_step_p3_create_schema(tenant, state)
            execute_step_p4_migrate_schema(tenant, state)

            owner, token_record, raw_token = create_tenant_owner_activation(
                tenant,
                owner_email=owner_email,
                owner_name="Dr. Token",
            )

            # Plain token exists in return value for delivery path, NOT stored in DB
            assert raw_token
            assert token_record.token_hash != raw_token
            assert check_password(raw_token, token_record.token_hash)

            # Check that raw token never appears in any column of the DB
            with schema_context(schema_name), connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT token_hash FROM "{schema_name}"."password_reset_token"'
                )
                rows = cursor.fetchall()
                assert len(rows) == 1
                assert raw_token not in rows[0][0]

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn08_idempotency_supersedes_predecessor_token_and_does_not_duplicate_owner(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "idempotentlab"
        schema_name = f"tenant_{slug}"
        owner_email = "owner@idempotent.pk"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Idempotent Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email=owner_email,
                        owner_name="Dr. Repeat",
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            state = get_provisioning_state(tenant)
            execute_step_p3_create_schema(tenant, state)
            execute_step_p4_migrate_schema(tenant, state)

            # Run 1
            owner_1, tok_1, raw_1 = create_tenant_owner_activation(
                tenant,
                owner_email=owner_email,
                owner_name="Dr. Repeat",
            )
            assert tok_1.used_at is None

            # Run 2 (resume / re-run)
            owner_2, tok_2, raw_2 = create_tenant_owner_activation(
                tenant,
                owner_email=owner_email,
                owner_name="Dr. Repeat",
            )

            with schema_context(schema_name):
                # Never creates a second Owner
                assert StaffUser.objects.count() == 1
                assert owner_1.id == owner_2.id

                # Two tokens exist: the predecessor was superseded, exactly one is live
                all_tokens = PasswordResetToken.objects.filter(
                    staff_user=owner_1,
                    purpose=PasswordResetToken.Purpose.ACTIVATION,
                ).order_by("created_at")
                assert all_tokens.count() == 2

                first_tok = all_tokens[0]
                second_tok = all_tokens[1]

                # Predecessor was superseded (used_at set to invalidate)
                assert first_tok.id == tok_1.id
                assert first_tok.used_at is not None

                # Fresh token is live
                assert second_tok.id == tok_2.id
                assert second_tok.used_at is None
                assert second_tok.token_hash != first_tok.token_hash
                assert raw_1 != raw_2

                # Never leave two simultaneously valid activation tokens for one Owner
                live_tokens = PasswordResetToken.objects.filter(
                    staff_user=owner_1,
                    purpose=PasswordResetToken.Purpose.ACTIVATION,
                    used_at__isnull=True,
                )
                assert live_tokens.count() == 1
                live_tok = live_tokens.first()
                assert live_tok is not None
                assert live_tok.id == tok_2.id

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn08_email_failure_does_not_block_owner_and_token_creation(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "mailfailab"
        schema_name = f"tenant_{slug}"
        owner_email = "owner@mailfail.pk"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Mail Fail Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email=owner_email,
                        owner_name="Dr. FailMail",
                        actor_id=sa.id,
                    )
                )

            tenant = res.tenant
            state = get_provisioning_state(tenant)
            execute_step_p3_create_schema(tenant, state)
            execute_step_p4_migrate_schema(tenant, state)

            caplog.set_level(logging.WARNING, logger="labflow.provisioning")
            with patch(
                "apps.platform.provisioning.send_mail",
                side_effect=RuntimeError("Simulated SMTP outage"),
            ):
                owner, tok, raw_tok = create_tenant_owner_activation(
                    tenant,
                    owner_email=owner_email,
                    owner_name="Dr. FailMail",
                )

            # Owner and activation token must be created despite email failure
            assert owner is not None
            assert tok is not None
            with schema_context(schema_name):
                assert StaffUser.objects.filter(email=owner_email).exists()
                assert PasswordResetToken.objects.filter(
                    staff_user=owner,
                    purpose=PasswordResetToken.Purpose.ACTIVATION,
                    used_at__isnull=True,
                ).exists()

            # Warning log was emitted
            assert any(
                "Failed to send owner activation email" in record.message
                for record in caplog.records
            )

        finally:
            _drop_schema_if_exists(schema_name)

    def test_tn08_full_provisioning_task_runs_p8_and_creates_owner(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "fullp8lab"
        schema_name = f"tenant_{slug}"
        owner_email = "owner@fullp8.pk"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Full P8 Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email=owner_email,
                        owner_name="Dr. Full",
                        actor_id=sa.id,
                    )
                )

            task_res = provision_tenant_task(slug)
            assert task_res["status"] == "active"
            assert "P-8" in task_res["completed_steps"]

            with schema_context(schema_name):
                owner = StaffUser.objects.get(email=owner_email)
                assert owner.role == Role.OWNER
                assert owner.branch is None
                assert owner.is_active is False
                assert owner.totp_enabled is False

                tok = PasswordResetToken.objects.get(
                    staff_user=owner,
                    purpose=PasswordResetToken.Purpose.ACTIVATION,
                    used_at__isnull=True,
                )
                assert tok.expires_at > timezone.now()

        finally:
            _drop_schema_if_exists(schema_name)
