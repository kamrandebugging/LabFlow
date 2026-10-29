from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.core.tenant_settings import TenantSetting
from django.db import connection
from django_tenants.utils import schema_context

from apps.billing.models import Invoice, Payment
from apps.branches.models import Branch
from apps.catalog.models import Panel, PanelTest, ReferenceRange, Test, TestPrice
from apps.notifications.models import NotificationTemplate
from apps.partners.models import (
    ReferralPartner,
    RevenueShareRule,
    Settlement,
    ShareLedgerEntry,
)
from apps.patients.models import Patient
from apps.platform.provisioning import (
    ProvisionTenantInput,
    create_tenant_provisioning,
    execute_step_p6_seed_data,
    execute_step_p7_settings_defaults,
    get_provisioning_state,
)
from apps.platform.tasks import provision_tenant_task
from apps.reports.models import Report
from apps.results.models import Result
from apps.samples.models import Sample
from tests.factories import PlanFactory, PlatformUserFactory


def _drop_schema_if_exists(schema_name: str) -> None:
    connection.set_schema_to_public()
    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


@pytest.mark.django_db(transaction=True)
class TestStepsP6AndP7SeedingAndA10Exclusion:
    """
    Subtask 5 (KAN-76 / TN-06): Seed starter catalogue, panel components,
    reference ranges, EN/UR notification templates, and default tenant settings
    via get_or_create, with strictly ZERO revenue_share_rule rows (A-10) and
    ZERO clinical/demo rows.
    """

    def test_tn06_p6_and_p7_seed_exact_catalogue_templates_settings_and_no_zero_percent_rule(  # noqa: E501
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        slug = "seedchecklab"
        schema_name = f"tenant_{slug}"

        try:
            with patch("apps.platform.provisioning.provision_tenant_task.delay"):
                res = create_tenant_provisioning(
                    ProvisionTenantInput(
                        name="Seed Check Lab",
                        slug=slug,
                        plan_id=plan.id,
                        owner_email="owner@seedcheck.pk",
                        owner_name="Dr. Seed",
                        actor_id=sa.id,
                    )
                )

            task_res = provision_tenant_task(slug)
            assert task_res["status"] == "active"
            assert "P-6" in task_res["completed_steps"]
            assert "P-7" in task_res["completed_steps"]

            with schema_context(schema_name):
                # 1. Default branch seeded
                assert Branch.objects.count() == 1
                hq = Branch.objects.get(code="HQ1")
                assert hq.is_collection_centre is False
                assert hq.result_entry_enabled is False

                # 2. Starter Panels (CBC, LFT, RFT, LIPID) + prices (Doc 02 §16)
                expected_panels = {
                    "CBC": Decimal("800.00"),
                    "LFT": Decimal("1800.00"),
                    "RFT": Decimal("1600.00"),
                    "LIPID": Decimal("2000.00"),
                }
                assert set(Panel.objects.values_list("code", flat=True)) == set(
                    expected_panels.keys()
                )
                for p_code, p_price in expected_panels.items():
                    tp = TestPrice.objects.get(panel__code=p_code, branch__isnull=True)
                    assert tp.price == p_price

                # 3. Component counts per panel (12 + 8 + 7 + 5 = 32)
                assert PanelTest.objects.filter(panel__code="CBC").count() == 12
                assert PanelTest.objects.filter(panel__code="LFT").count() == 8
                assert PanelTest.objects.filter(panel__code="RFT").count() == 7
                assert PanelTest.objects.filter(panel__code="LIPID").count() == 5
                assert PanelTest.objects.count() == 32

                # 4. Standalone starter tests (HBA1C, BSF, BSR, URE, TSH) + prices
                expected_standalone = {
                    "HBA1C": Decimal("1500.00"),
                    "BSF": Decimal("400.00"),
                    "BSR": Decimal("350.00"),
                    "URE": Decimal("600.00"),
                    "TSH": Decimal("1800.00"),
                }
                for t_code, t_price in expected_standalone.items():
                    tp = TestPrice.objects.get(test__code=t_code, branch__isnull=True)
                    assert tp.price == t_price

                # Total tests = 32 components + 5 standalone = 37 tests
                assert Test.objects.count() == 37

                # Reference ranges: adult-M and adult-F (age_min_days=6570)
                for test_obj in Test.objects.all():
                    assert ReferenceRange.objects.filter(
                        test=test_obj, sex="M", age_min_days=6570
                    ).exists()
                    assert ReferenceRange.objects.filter(
                        test=test_obj, sex="F", age_min_days=6570
                    ).exists()

                # 5. Notification templates in en and ur for all 4 keys (16 total)
                expected_keys = {
                    "sample_collected",
                    "report_ready",
                    "report_link_resend",
                    "settlement_ready",
                }
                for key in expected_keys:
                    for loc in ("en", "ur"):
                        for ch in ("email", "whatsapp"):
                            assert NotificationTemplate.objects.filter(
                                key=key, locale=loc, channel=ch
                            ).exists()
                assert NotificationTemplate.objects.count() == 16

                # 6. Tenant settings registry defaults (Doc 04 §10.2)
                settings_map = dict(TenantSetting.objects.values_list("key", "value"))
                assert settings_map == {
                    "billing_hold_enabled": "false",
                    "report_default_language": "en",
                    "report_link_validity_days": "7",
                    "transfer_late_after_hours": "24",
                    "brand_display_name": "Seed Check Lab",
                    "brand_accent_colour": "#0d9488",
                }

                # 7. A-10 Exclusion: ZERO revenue_share_rule rows, ZERO demo rows
                assert RevenueShareRule.objects.count() == 0
                assert ReferralPartner.objects.count() == 0
                assert ShareLedgerEntry.objects.count() == 0
                assert Settlement.objects.count() == 0
                assert Patient.objects.count() == 0
                assert Invoice.objects.count() == 0
                assert Payment.objects.count() == 0
                assert Sample.objects.count() == 0
                assert Result.objects.count() == 0
                assert Report.objects.count() == 0

                counts_Snapshot = (
                    Branch.objects.count(),
                    Panel.objects.count(),
                    Test.objects.count(),
                    PanelTest.objects.count(),
                    TestPrice.objects.count(),
                    ReferenceRange.objects.count(),
                    NotificationTemplate.objects.count(),
                    TenantSetting.objects.count(),
                )

            # 8. Re-running P-6 and P-7 directly creates ZERO duplicate rows
            state = get_provisioning_state(res.tenant)
            execute_step_p6_seed_data(res.tenant, state)
            execute_step_p7_settings_defaults(res.tenant, state)

            with schema_context(schema_name):
                counts_after_rerun = (
                    Branch.objects.count(),
                    Panel.objects.count(),
                    Test.objects.count(),
                    PanelTest.objects.count(),
                    TestPrice.objects.count(),
                    ReferenceRange.objects.count(),
                    NotificationTemplate.objects.count(),
                    TenantSetting.objects.count(),
                )
                assert counts_after_rerun == counts_Snapshot
                assert RevenueShareRule.objects.count() == 0
        finally:
            _drop_schema_if_exists(schema_name)
