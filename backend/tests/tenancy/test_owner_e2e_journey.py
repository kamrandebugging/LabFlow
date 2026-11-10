"""End-to-End Owner Journey Test Suite (Phase 5).

Verifies the complete 8-step Owner journey on a fresh tenant with zero errors:
1. Log in with credentials & session -> context & dashboard loaded with real data.
2. Create patient -> appears in patient list.
3. Create invoice picking test from catalog -> invoice created, daily total real.
4. Collect sample for invoice -> appears in samples list, received into worklist.
5. Enter result as Owner -> result entered, sample becomes in_process.
6. Approve report/result as Owner -> approval succeeds, audit log records Owner.
7. Tenant Settings brand display name is real lab name; catalog has 150 tests.
8. Silent token refresh -> rotated access token succeeds with zero errors.
"""

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import Client
from django_tenants.utils import schema_context, tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from apps.catalog.models import Test
from apps.core.models import Domain, Tenant
from apps.platform.provisioning import (
    ProvisionTenantInput,
    create_tenant_provisioning,
)
from apps.platform.tasks import provision_tenant_task
from tests.factories import PlanFactory, PlatformUserFactory


@pytest.mark.django_db(transaction=True)
def test_full_owner_e2e_journey_fresh_tenant() -> None:
    sa = PlatformUserFactory(totp_enabled=True, is_active=True)
    plan = PlanFactory(is_active=True)
    slug = f"apex{uuid.uuid4().hex[:6]}"
    schema_name = f"tenant_{slug}"

    try:
        with patch(
            "apps.reports.tasks.render_report_pdf", return_value=b"%PDF-1.4 mock"
        ):
            # Step 0: Provision brand new tenant "Apex Diagnostics"
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Apex Diagnostics",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@apexdiag.pk",
                        owner_name="Dr. Tariq Apex",
                        actor_id=sa.id,
                    )
                )

            task_res = provision_tenant_task(slug)
            assert task_res["status"] == "active"
            tenant = Tenant.objects.get(slug=slug)

            Domain.objects.get_or_create(
                tenant=tenant,
                domain=f"{slug}.localhost",
                defaults={"is_primary": False},
            )

            client = Client(HTTP_HOST=f"{slug}.localhost")

            # Step 1: Owner login & session creation
            with tenant_context(tenant):
                owner = StaffUser.objects.get(email="owner@apexdiag.pk")
                assert owner.role == Role.OWNER
                # This journey starts after onboarding: a real Owner completes
                # the temp-password change and mandatory TOTP enrolment before
                # using the lab. Mirror that state so a refresh cannot
                # downgrade the session to onboarding-only.
                owner.totp_enabled = True
                owner.password_is_temporary = False
                owner.save(
                    update_fields=[
                        "totp_enabled",
                        "password_is_temporary",
                        "updated_at",
                    ]
                )
                session = AuthService.create_session(user=owner, tenant_id=slug)
                access_token = session["access"]
                auth_hdr = {"Authorization": f"Bearer {access_token}"}

            # Verify context loads real data
            ctx_res = client.get("/api/v1/auth/tenant", headers=auth_hdr)
            assert ctx_res.status_code == 200
            assert ctx_res.json()["tenant"]["name"] == "Apex Diagnostics"

            # Step 2: Create a patient
            with schema_context(schema_name):
                from apps.branches.models import Branch

                branch = Branch.objects.first()
                assert branch is not None
                branch_id = str(branch.id)

            patient_payload = {
                "name": "Kamran Akmal",
                "phone": "03001234567",
                "sex": "M",
                "date_of_birth": "1990-05-15",
                "branch_id": branch_id,
            }
            pat_res = client.post(
                "/api/v1/patients",
                data=patient_payload,
                content_type="application/json",
                headers=auth_hdr,
            )
            assert pat_res.status_code == 201
            patient_id = pat_res.json()["id"]

            # Verify patient appears in list
            list_pat_res = client.get("/api/v1/patients", headers=auth_hdr)
            assert list_pat_res.status_code == 200
            patients = list_pat_res.json()
            assert any(p["id"] == patient_id for p in patients)

            # Step 3: Create an invoice (pick test from catalog)
            cat_res = client.get("/api/v1/tests?is_active=true", headers=auth_hdr)
            assert cat_res.status_code == 200
            cat_tests = cat_res.json()
            # Find HBA1C or another test
            hba1c = next((t for t in cat_tests if t["code"] == "HBA1C"), cat_tests[0])
            test_id = hba1c["id"]
            test_price = hba1c.get("effective_price") or hba1c.get("price") or 1500.00

            inv_payload = {
                "patient_id": patient_id,
                "branch_id": branch_id,
                "referral_partner_id": None,
                "items": [
                    {
                        "test_id": test_id,
                        "qty": 1,
                    }
                ],
                "discount_amount": "0.00",
                "discount_reason": None,
            }
            inv_res = client.post(
                "/api/v1/invoices",
                data=inv_payload,
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                headers=auth_hdr,
            )
            assert inv_res.status_code == 201, inv_res.content
            invoice_id = inv_res.json()["id"]

            # Verify daily total is real from invoices list
            list_inv_res = client.get("/api/v1/invoices", headers=auth_hdr)
            assert list_inv_res.status_code == 200
            daily_total = list_inv_res.json().get("daily_total")
            assert Decimal(daily_total) >= Decimal(str(test_price))

            # Post payment to invoice
            pay_payload = {
                "kind": "payment",
                "method": "cash",
                "amount": str(test_price),
            }
            pay_res = client.post(
                f"/api/v1/invoices/{invoice_id}/payments",
                data=pay_payload,
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                headers=auth_hdr,
            )
            assert pay_res.status_code == 201

            # Step 4: Collect sample for invoice
            sample_payload = {
                "invoice_id": invoice_id,
            }
            smp_res = client.post(
                "/api/v1/samples",
                data=sample_payload,
                content_type="application/json",
                headers=auth_hdr,
            )
            assert smp_res.status_code == 201
            sample_id = smp_res.json()["id"]

            # Receive sample into worklist
            rec_res = client.post(
                f"/api/v1/samples/{sample_id}/receive",
                data={},
                content_type="application/json",
                headers=auth_hdr,
            )
            assert rec_res.status_code == 200
            sample_data = rec_res.json()
            assert sample_data["status"] == "received"

            # Verify sample detail returns sample_tests
            detail_res = client.get(f"/api/v1/samples/{sample_id}", headers=auth_hdr)
            assert detail_res.status_code == 200
            s_tests = detail_res.json().get("sample_tests", [])
            assert len(s_tests) > 0

            # Step 5: Enter result as Owner
            result_payload = {
                "results": [
                    {
                        "test_id": test_id,
                        "value": "5.4",
                        "unit": "%",
                    }
                ]
            }
            entry_res = client.post(
                f"/api/v1/samples/{sample_id}/results",
                data=result_payload,
                content_type="application/json",
                headers=auth_hdr,
            )
            assert entry_res.status_code in (200, 201)
            results_resp = entry_res.json()
            result_id = results_resp["results"][0]["id"]

            # Step 6: Approve report/result as Owner (Self-approval superrole)
            approve_payload = {
                "decision": "approved",
            }
            app_res = client.post(
                f"/api/v1/results/{result_id}/approve",
                data=approve_payload,
                content_type="application/json",
                headers=auth_hdr,
            )
            assert app_res.status_code == 200
            app_data = app_res.json()
            assert app_data["status"] == "approved"

            # Verify audit log records Owner + timestamp
            with schema_context(schema_name):
                audit = AuditLog.objects.filter(
                    action="result.approved",
                    entity_id=result_id,
                ).first()
                assert audit is not None
                assert audit.actor_id == owner.id
                assert (audit.after_jsonb or {}).get(
                    "audit_note"
                ) == "owner_self_approval"

            # Step 7: Tenant settings brand name & 150 tests catalog
            settings_res = client.get("/api/v1/settings", headers=auth_hdr)
            assert settings_res.status_code == 200
            brand_name = settings_res.json()["settings"]["brand_display_name"]["value"]
            assert brand_name == "Apex Diagnostics"

            with schema_context(schema_name):
                assert Test.objects.count() == 150

            # Step 8: Silent refresh of token
            refresh_token = session["refresh_token"]
            client.cookies["refresh_token"] = refresh_token
            ref_res = client.post("/api/v1/auth/refresh")
            assert ref_res.status_code == 200
            new_access = ref_res.json()["access"]
            assert new_access is not None

            # Verify new access token works with zero errors
            new_auth_hdr = {"Authorization": f"Bearer {new_access}"}
            verify_res = client.get("/api/v1/patients", headers=new_auth_hdr)
            assert verify_res.status_code == 200
    finally:
        connection.set_schema_to_public()
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
