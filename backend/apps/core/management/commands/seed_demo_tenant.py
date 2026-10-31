"""Management command to seed demo tenants and operator (Doc 09 §16.3).

Seeds:
1. Platform Operator (Super Admin PlatformUser in public schema) with TOTP.
2. Two demo tenants (Doc 09 §16.3: isolation visible locally):
   - demo-isb ("Capital Diagnostic Centre", slug "demo-isb")
   - demo-lhr ("Punjab Clinical Labs", slug "demo-lhr")
3. Branches (including 1 collection centre per Doc 09 §16.3 & Doc 04 §8.1).
4. Staff in every role with TOTP for Owner, Manager, Pathologist.
5. Starter catalogue, test panels, prices, and reference ranges.
6. Referral partners with tiered revenue-share rules (Doc 05 §7).
7. Synthetic patients and samples in all state machine states.
8. Formatted summary printed to stdout.
"""

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from apps.accounts.models import Role, StaffBranch, StaffUser
from apps.billing.models import Invoice, InvoiceItem
from apps.branches.models import Branch
from apps.catalog.models import Test
from apps.core.models import Domain, PlatformUser, Tenant
from apps.partners.models import ReferralPartner, RevenueShareRule
from apps.patients.models import Patient
from apps.platform.seeds import seed_tenant_p6_data, seed_tenant_p7_settings
from apps.results.models import Result
from apps.samples.models import Sample, SampleTest


class Command(BaseCommand):
    """Seed demo tenants and platform test harness data."""

    help = "Seed demo tenants, roles, TOTP, catalogue, samples (Doc 09 §16.3)"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Purge and recreate demo tenants if they already exist",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force execution in production or non-DEBUG mode",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        is_production = os.environ.get("DJANGO_ENV", "").lower() in (
            "production",
            "prod",
        ) or os.environ.get("ENVIRONMENT", "").lower() in ("production", "prod")
        if is_production and not options.get("force", False):
            raise CommandError(
                "seed_demo_tenant cannot run in production without --force."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "==> Starting LabFlow Demo Harness Seeding (Doc 09 §16.3)..."
            )
        )

        fernet = Fernet(settings.LABFLOW_TOTP_ENCRYPTION_KEY.encode())

        # 1. Platform Operator (Super Admin in public schema)
        operator_creds = self._seed_platform_operator(fernet)

        # 2. Demo Tenants Configuration
        tenants_config = [
            {
                "slug": "demo-isb",
                "name": "Capital Diagnostic Centre",
                "schema_name": "tenant_demo_isb",
                "domain": "demo-isb.localhost",
                "main_branch_code": "ISB",
                "col_branch_code": "SAT",
            },
            {
                "slug": "demo-lhr",
                "name": "Punjab Clinical Labs",
                "schema_name": "tenant_demo_lhr",
                "domain": "demo-lhr.localhost",
                "main_branch_code": "LHR",
                "col_branch_code": "COL",
            },
        ]

        tenant_reports: list[dict[str, Any]] = []

        for t_conf in tenants_config:
            t_report = self._seed_single_tenant(
                t_conf, fernet, reset=options.get("reset", False)
            )
            tenant_reports.append(t_report)

        # 3. Print Output Summary
        self._print_summary(operator_creds, tenant_reports)

    def _seed_platform_operator(self, fernet: Fernet) -> dict[str, str]:
        """Seed platform Super Admin operator in public schema."""
        email = "admin@labflow.platform"
        raw_password = "PlatformAdmin2026!"
        totp_secret = "JBSWY3DPEHPK3PXP"

        encrypted_secret = fernet.encrypt(totp_secret.encode()).decode()
        backup_codes = [
            "A1B2C3D4",
            "E5F6G7H8",
            "J9K0L1M2",
            "N3P4Q5R6",
            "S7T8U9V0",
            "W1X2Y3Z4",
            "B5C6D7E8",
            "F9G0H1J2",
            "K3L4M5N6",
            "P7Q8R9S0",
        ]
        hashed_backup_codes = [make_password(c) for c in backup_codes]

        PlatformUser.objects.update_or_create(
            email=email,
            defaults={
                "password_hash": make_password(raw_password),
                "totp_secret_encrypted": encrypted_secret,
                "totp_backup_codes_hash": hashed_backup_codes,
                "totp_enabled": True,
                "is_active": True,
            },
        )
        return {
            "email": email,
            "password": raw_password,
            "totp_secret": totp_secret,
        }

    def _seed_single_tenant(
        self, conf: dict[str, Any], fernet: Fernet, reset: bool
    ) -> dict[str, Any]:
        """Seed one demo tenant with branches, catalogue, staff, partners."""
        slug = conf["slug"]
        name = conf["name"]
        domain_name = conf["domain"]
        schema_name = conf["schema_name"]

        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant and reset:
            self.stdout.write(f"Resetting existing tenant {slug}...")
            tenant.delete()
            tenant = None

        if not tenant:
            tenant = Tenant.objects.create(
                slug=slug,
                name=name,
                schema_name=schema_name,
                status=Tenant.Status.ACTIVE,
            )
            Domain.objects.get_or_create(
                tenant=tenant,
                domain=domain_name,
                defaults={"is_primary": True},
            )
        else:
            if tenant.status != Tenant.Status.ACTIVE:
                tenant.status = Tenant.Status.ACTIVE
                tenant.save(update_fields=["status"])
            Domain.objects.get_or_create(
                tenant=tenant,
                domain=domain_name,
                defaults={"is_primary": True},
            )

        # Seed catalogue and settings
        seed_tenant_p6_data(tenant)
        seed_tenant_p7_settings(tenant)

        staff_list: list[dict[str, str]] = []

        with schema_context(tenant.schema_name):
            # Seed Branches
            main_branch, _ = Branch.objects.get_or_create(
                code=conf["main_branch_code"],
                defaults={
                    "name": f"{name} - Main Laboratory",
                    "address": "Blue Area, Main Boulevard",
                    "phone": "+92-51-111-222-333",
                    "is_collection_centre": False,
                    "result_entry_enabled": True,
                },
            )
            col_branch, _ = Branch.objects.get_or_create(
                code=conf["col_branch_code"],
                defaults={
                    "name": f"{name} - Satellite Collection Centre",
                    "address": "Sector F-10 Commercial Area",
                    "phone": "+92-51-444-555-666",
                    "is_collection_centre": True,
                    "result_entry_enabled": False,
                },
            )

            # Seed Staff Users in every role
            roles_data = [
                ("owner", Role.OWNER, f"owner@{slug}.com", "OwnerDemoPass2026!", True),
                (
                    "manager",
                    Role.MANAGER,
                    f"manager@{slug}.com",
                    "ManagerDemoPass2026!",
                    True,
                ),
                (
                    "pathologist",
                    Role.PATHOLOGIST,
                    f"pathologist@{slug}.com",
                    "PathoDemoPass2026!",
                    True,
                ),
                (
                    "technician",
                    Role.TECHNICIAN,
                    f"technician@{slug}.com",
                    "TechDemoPass2026!",
                    False,
                ),
                (
                    "reception",
                    Role.RECEPTION,
                    f"receptionist@{slug}.com",
                    "RecepDemoPass2026!",
                    False,
                ),
            ]

            created_staff_map: dict[str, StaffUser] = {}

            for label, role_val, s_email, s_pass, requires_totp in roles_data:
                totp_secret = "JBSWY3DPEHPK3PXP" if requires_totp else ""
                enc_secret = (
                    fernet.encrypt(totp_secret.encode()).decode()
                    if requires_totp
                    else None
                )
                b_codes = (
                    [make_password(f"BACKUP{i}") for i in range(10)]
                    if requires_totp
                    else None
                )

                s_user, _ = StaffUser.objects.update_or_create(
                    email=s_email,
                    defaults={
                        "branch": (
                            main_branch if role_val != Role.RECEPTION else col_branch
                        ),
                        "role": role_val,
                        "password_hash": make_password(s_pass),
                        "totp_secret_encrypted": enc_secret,
                        "totp_backup_codes_hash": b_codes,
                        "totp_enabled": requires_totp,
                        "is_active": True,
                    },
                )
                StaffBranch.objects.get_or_create(
                    staff_user=s_user,
                    branch=main_branch,
                    defaults={"is_primary": True},
                )
                created_staff_map[label] = s_user
                staff_list.append(
                    {
                        "role": role_val,
                        "email": s_email,
                        "password": s_pass,
                        "totp": totp_secret if requires_totp else "N/A",
                    }
                )

            # Seed Referral Partners & Revenue-Share Rules
            p1, _ = ReferralPartner.objects.get_or_create(
                name="Dr. Tariq Aziz",
                defaults={
                    "organisation": "Aziz Family Clinic",
                    "phone": "+923001234567",
                    "email": f"dr.aziz@{slug}.com",
                    "is_active": True,
                },
            )
            p2, _ = ReferralPartner.objects.get_or_create(
                name="Shifa Medical Complex",
                defaults={
                    "organisation": "Shifa Health",
                    "phone": "+923007654321",
                    "email": f"referrals.shifa@{slug}.com",
                    "is_active": True,
                },
            )

            today = date.today()
            # Tiered rules: category+branch, category, partner-wide
            RevenueShareRule.objects.get_or_create(
                referral_partner=p1,
                test_category="Biochemistry",
                branch=main_branch,
                defaults={
                    "percent": Decimal("20.00"),
                    "effective_from": today - timedelta(days=30),
                },
            )
            RevenueShareRule.objects.get_or_create(
                referral_partner=p1,
                test_category="Haematology",
                branch=None,
                defaults={
                    "percent": Decimal("15.00"),
                    "effective_from": today - timedelta(days=30),
                },
            )
            RevenueShareRule.objects.get_or_create(
                referral_partner=p2,
                test_category=None,
                branch=None,
                defaults={
                    "percent": Decimal("10.00"),
                    "effective_from": today - timedelta(days=30),
                },
            )

            # Seed Synthetic Patients
            patients_info = [
                (
                    "MRN-26-000001",
                    "Muhammad Ahmed",
                    "+923001111111",
                    Patient.Sex.MALE,
                    date(1985, 4, 12),
                ),
                (
                    "MRN-26-000002",
                    "Fatima Bibi",
                    "+923002222222",
                    Patient.Sex.FEMALE,
                    date(1992, 8, 23),
                ),
                (
                    "MRN-26-000003",
                    "Zainab Khan",
                    "+923003333333",
                    Patient.Sex.FEMALE,
                    date(2001, 11, 5),
                ),
                (
                    "MRN-26-000004",
                    "Ali Raza",
                    "+923004444444",
                    Patient.Sex.MALE,
                    date(1978, 1, 30),
                ),
                (
                    "MRN-26-000005",
                    "Usman Tariq",
                    "+923005555555",
                    Patient.Sex.MALE,
                    date(1995, 6, 18),
                ),
            ]
            patients = []
            for mrn, p_name, phone, sex, dob in patients_info:
                p_obj, _ = Patient.objects.get_or_create(
                    mrn=mrn,
                    defaults={
                        "branch": main_branch,
                        "name": p_name,
                        "phone": phone,
                        "sex": sex,
                        "date_of_birth": dob,
                    },
                )
                patients.append(p_obj)

            # Seed Billing Invoices & Items for Samples
            tests_qs = list(Test.objects.all()[:4])
            now_dt = datetime.now(UTC)

            sample_states = [
                (Sample.Status.COLLECTED, "ACC-26-000001", None),
                (Sample.Status.RECEIVED, "ACC-26-000002", None),
                (Sample.Status.IN_PROCESS, "ACC-26-000003", None),
                (Sample.Status.READY, "ACC-26-000004", None),
                (
                    Sample.Status.REJECTED,
                    "ACC-26-000005",
                    Sample.RejectionReasonCode.HEMUSHED,
                ),
                (Sample.Status.CANCELLED, "ACC-26-000006", None),
            ]

            receptionist = created_staff_map["reception"]
            technician = created_staff_map["technician"]

            for idx, (st_val, acc_id, rej_reason) in enumerate(sample_states):
                inv, _ = Invoice.objects.get_or_create(
                    idempotency_key=f"inv-seed-{slug}-{idx}",
                    defaults={
                        "patient": patients[idx % len(patients)],
                        "branch": main_branch,
                        "referral_partner": p1 if idx % 2 == 0 else p2,
                        "status": (
                            Invoice.Status.PAID
                            if st_val in (Sample.Status.READY, Sample.Status.IN_PROCESS)
                            else Invoice.Status.UNPAID
                        ),
                        "subtotal": Decimal("1500.00"),
                        "total": Decimal("1500.00"),
                    },
                )
                inv_item, _ = InvoiceItem.objects.get_or_create(
                    invoice=inv,
                    defaults={
                        "test": tests_qs[idx % len(tests_qs)] if tests_qs else None,
                        "description": "Diagnostic Laboratory Test",
                        "unit_price": Decimal("1500.00"),
                        "quantity": 1,
                        "line_total": Decimal("1500.00"),
                    },
                )

                s_obj, _ = Sample.objects.get_or_create(
                    accession_id=acc_id,
                    defaults={
                        "invoice": inv,
                        "branch": main_branch,
                        "status": st_val,
                        "collected_at": now_dt - timedelta(hours=idx * 2 + 1),
                        "collected_by": receptionist,
                        "rejection_reason_code": rej_reason,
                        "rejection_note": (
                            "Specimen hemolyzed during collection"
                            if rej_reason
                            else None
                        ),
                    },
                )

                if tests_qs:
                    target_test = tests_qs[idx % len(tests_qs)]
                    SampleTest.objects.get_or_create(
                        sample=s_obj,
                        test=target_test,
                        defaults={"invoice_item": inv_item},
                    )

            # Seed Results in all 5 states
            if tests_qs:
                res_sample = Sample.objects.filter(status=Sample.Status.READY).first()
                if not res_sample:
                    res_sample = Sample.objects.first()

                result_states = [
                    (Result.Status.ENTERED, Result.Flag.NORMAL, "14.2"),
                    (Result.Status.APPROVED, Result.Flag.HIGH, "18.5"),
                    (Result.Status.REJECTED, Result.Flag.CRITICAL, "25.0"),
                    (Result.Status.AMENDED, Result.Flag.NORMAL, "13.9"),
                    (Result.Status.WITHDRAWN, None, "0.0"),
                ]

                unit_val = tests_qs[0].unit if hasattr(tests_qs[0], "unit") else "g/dL"
                for r_status, r_flag, r_val in result_states:
                    Result.objects.get_or_create(
                        sample=res_sample,
                        test=tests_qs[0],
                        status=r_status,
                        defaults={
                            "value": r_val,
                            "unit": unit_val,
                            "flag": r_flag,
                            "entered_by": technician,
                        },
                    )

        return {
            "slug": slug,
            "name": name,
            "domain": domain_name,
            "staff": staff_list,
        }

    def _print_summary(
        self, op_creds: dict[str, str], tenant_reports: list[dict[str, Any]]
    ) -> None:
        """Print clean summary box with credentials and TOTP setup keys."""
        line = "=" * 78
        self.stdout.write(self.style.SUCCESS("\n" + line))
        self.stdout.write(
            self.style.SUCCESS(
                "  LABFLOW LOCAL DEMO HARNESS SEEDED SUCCESSFULLY (Doc 09 §16.3)"
            )
        )
        self.stdout.write(self.style.SUCCESS(line))

        self.stdout.write("\n[1] PLATFORM OPERATOR (Super Admin):")
        self.stdout.write(f"    - Email:       {op_creds['email']}")
        self.stdout.write(f"    - Password:    {op_creds['password']}")
        self.stdout.write(f"    - TOTP Secret: {op_creds['totp_secret']}")

        for t_idx, t in enumerate(tenant_reports, 1):
            self.stdout.write(
                f"\n[{t_idx + 1}] DEMO TENANT: {t['name']} ({t['domain']})"
            )
            self.stdout.write(
                f"    Schema: tenant_{t['slug']} | URL: http://{t['domain']}"
            )
            self.stdout.write("    Staff Accounts:")
            for s in t["staff"]:
                totp_str = f" | TOTP: {s['totp']}" if s["totp"] != "N/A" else ""
                role_upper = s["role"].upper()
                self.stdout.write(
                    f"      * [{role_upper}] {s['email']} / {s['password']}{totp_str}"
                )

        self.stdout.write(self.style.SUCCESS("\n" + line + "\n"))
