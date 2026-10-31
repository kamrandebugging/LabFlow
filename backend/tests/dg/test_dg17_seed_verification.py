"""Scenario DG-17 verification test per Doc 09 §18.

Verbatim from Doc 09 §18:
Scenario: Fresh clone → make up → make seed
Expected: Demo tenants usable, all roles login, TOTP accounts per §16.3
"""

from __future__ import annotations

import io

import pytest
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django_tenants.utils import schema_context

from apps.accounts.models import Role, StaffUser
from apps.branches.models import Branch
from apps.catalog.models import Panel, Test
from apps.core.models import Domain, PlatformUser, Tenant
from apps.partners.models import ReferralPartner, RevenueShareRule
from apps.patients.models import Patient
from apps.results.models import Result
from apps.samples.models import Sample


@pytest.mark.django_db
class TestDG17SeedVerification:
    """DG-17: Test harness demo tenants seed verification suite."""

    def test_seed_demo_tenant_execution_and_idempotency(self) -> None:
        """Verify seed_demo_tenant runs successfully and is idempotent."""
        out = io.StringIO()
        call_command("seed_demo_tenant", stdout=out)
        output = out.getvalue()

        assert "LABFLOW LOCAL DEMO HARNESS SEEDED SUCCESSFULLY" in output
        assert "Capital Diagnostic Centre" in output
        assert "Punjab Clinical Labs" in output
        assert "admin@labflow.platform" in output

        # Second run must execute cleanly without unique constraint errors
        out_second = io.StringIO()
        call_command("seed_demo_tenant", stdout=out_second)
        assert "LABFLOW LOCAL DEMO HARNESS SEEDED SUCCESSFULLY" in out_second.getvalue()

    def test_platform_operator_totp_enrolled(self) -> None:
        """Verify Super Admin operator created with TOTP enrolled."""
        call_command("seed_demo_tenant")

        operator = PlatformUser.objects.filter(email="admin@labflow.platform").first()
        assert operator is not None
        assert operator.is_active is True
        assert operator.totp_enabled is True
        assert operator.totp_secret_encrypted is not None
        assert operator.totp_backup_codes_hash is not None
        assert len(operator.totp_backup_codes_hash) == 10
        assert operator.check_password("PlatformAdmin2026!") is True

    def test_demo_tenants_and_branches_isolation(self) -> None:
        """Verify 2 demo tenants exist with main branch and collection."""
        call_command("seed_demo_tenant")

        isb_tenant = Tenant.objects.filter(slug="demo-isb").first()
        lhr_tenant = Tenant.objects.filter(slug="demo-lhr").first()

        assert isb_tenant is not None
        assert isb_tenant.status == Tenant.Status.ACTIVE
        assert lhr_tenant is not None
        assert lhr_tenant.status == Tenant.Status.ACTIVE

        assert Domain.objects.filter(
            tenant=isb_tenant, domain="demo-isb.localhost"
        ).exists()
        assert Domain.objects.filter(
            tenant=lhr_tenant, domain="demo-lhr.localhost"
        ).exists()

        # Check branches in demo-isb
        with schema_context(isb_tenant.schema_name):
            main_branch = Branch.objects.filter(code="ISB").first()
            assert main_branch is not None
            assert main_branch.is_collection_centre is False
            assert main_branch.result_entry_enabled is True

            col_branch = Branch.objects.filter(code="SAT").first()
            assert col_branch is not None
            assert col_branch.is_collection_centre is True
            assert col_branch.result_entry_enabled is False

    def test_all_roles_login_and_totp_enrolment(self) -> None:
        """Verify staff in all 5 roles can authenticate."""
        call_command("seed_demo_tenant")

        tenant = Tenant.objects.filter(slug="demo-isb").first()
        assert tenant is not None

        expected_roles = {
            "owner@demo-isb.com": (Role.OWNER, "OwnerDemoPass2026!", True),
            "manager@demo-isb.com": (Role.MANAGER, "ManagerDemoPass2026!", True),
            "pathologist@demo-isb.com": (
                Role.PATHOLOGIST,
                "PathoDemoPass2026!",
                True,
            ),
            "technician@demo-isb.com": (
                Role.TECHNICIAN,
                "TechDemoPass2026!",
                False,
            ),
            "receptionist@demo-isb.com": (
                Role.RECEPTION,
                "RecepDemoPass2026!",
                False,
            ),
        }

        with schema_context(tenant.schema_name):
            for email, (
                role,
                pwd,
                requires_totp,
            ) in expected_roles.items():
                staff = StaffUser.objects.filter(email=email).first()
                assert staff is not None, f"Missing staff: {email}"
                assert staff.role == role
                assert staff.is_active is True
                assert check_password(pwd, staff.password_hash) is True
                assert staff.totp_enabled is requires_totp
                if requires_totp:
                    assert staff.totp_secret_encrypted is not None
                    assert staff.totp_backup_codes_hash is not None
                    assert len(staff.totp_backup_codes_hash) == 10

    def test_catalogue_and_partners_seeded(self) -> None:
        """Verify diagnostic catalogue and referral partners with rules."""
        call_command("seed_demo_tenant")

        tenant = Tenant.objects.filter(slug="demo-isb").first()
        assert tenant is not None

        with schema_context(tenant.schema_name):
            assert Test.objects.count() >= 10
            assert Panel.objects.count() >= 4
            assert ReferralPartner.objects.count() >= 2
            assert RevenueShareRule.objects.count() >= 3

    def test_synthetic_samples_and_results_all_states(self) -> None:
        """Verify synthetic samples in all 6 states and results in all 5."""
        call_command("seed_demo_tenant")

        tenant = Tenant.objects.filter(slug="demo-isb").first()
        assert tenant is not None

        with schema_context(tenant.schema_name):
            assert Patient.objects.count() >= 5

            # Assert all 6 sample states present
            sample_statuses = set(Sample.objects.values_list("status", flat=True))
            for st in (
                "collected",
                "received",
                "in_process",
                "ready",
                "rejected",
                "cancelled",
            ):
                assert st in sample_statuses, f"Sample state {st} missing"

            # Assert all 5 result states present
            result_statuses = set(Result.objects.values_list("status", flat=True))
            for rs in (
                "entered",
                "approved",
                "rejected",
                "amended",
                "withdrawn",
            ):
                assert rs in result_statuses, f"Result state {rs} missing"
