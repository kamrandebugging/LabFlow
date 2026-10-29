from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from django_tenants.utils import schema_context

from apps.branches.models import Branch
from apps.catalog.models import Panel, PanelTest, ReferenceRange, Test, TestPrice
from apps.core.models import Tenant
from apps.core.tenant_settings import TenantSetting
from apps.notifications.models import NotificationTemplate

ADULT_MIN_DAYS = 6570  # 18 years in days (Doc 02 §10, §16)

STARTER_PANELS: tuple[tuple[str, str, Decimal], ...] = (
    ("CBC", "Complete Blood Count", Decimal("800.00")),
    ("LFT", "Liver Function Tests", Decimal("1800.00")),
    ("RFT", "Renal Function Tests", Decimal("1600.00")),
    ("LIPID", "Lipid Profile", Decimal("2000.00")),
)

STARTER_STANDALONE_TESTS: tuple[
    tuple[str, str, str, str, Decimal, Decimal, Decimal, Decimal, Decimal], ...
] = (
    # code, name, category, unit, price, m_low, m_high, f_low, f_high
    (
        "HBA1C",
        "HbA1c",
        "Biochemistry",
        "%",
        Decimal("1500.00"),
        Decimal("4.000"),
        Decimal("5.600"),
        Decimal("4.000"),
        Decimal("5.600"),
    ),
    (
        "BSF",
        "Blood Sugar (Fasting)",
        "Biochemistry",
        "mg/dL",
        Decimal("400.00"),
        Decimal("70.000"),
        Decimal("99.000"),
        Decimal("70.000"),
        Decimal("99.000"),
    ),
    (
        "BSR",
        "Blood Sugar (Random)",
        "Biochemistry",
        "mg/dL",
        Decimal("350.00"),
        Decimal("70.000"),
        Decimal("140.000"),
        Decimal("70.000"),
        Decimal("140.000"),
    ),
    (
        "URE",
        "Urine R/E",
        "Clinical Pathology",
        "pH",
        Decimal("600.00"),
        Decimal("4.500"),
        Decimal("8.000"),
        Decimal("4.500"),
        Decimal("8.000"),
    ),
    (
        "TSH",
        "TSH",
        "Endocrinology",
        "mIU/L",
        Decimal("1800.00"),
        Decimal("0.400"),
        Decimal("4.000"),
        Decimal("0.400"),
        Decimal("4.000"),
    ),
)

PANEL_COMPONENT_TESTS: dict[
    str,
    tuple[tuple[str, str, str, str, Decimal, Decimal, Decimal, Decimal], ...],
] = {
    "CBC": (
        (
            "HB",
            "Haemoglobin",
            "Haematology",
            "g/dL",
            Decimal("13.500"),
            Decimal("17.500"),
            Decimal("12.000"),
            Decimal("15.500"),
        ),
        (
            "RBC",
            "Red Blood Cell Count",
            "Haematology",
            "10^6/uL",
            Decimal("4.500"),
            Decimal("5.900"),
            Decimal("4.000"),
            Decimal("5.200"),
        ),
        (
            "HCT",
            "Haematocrit",
            "Haematology",
            "%",
            Decimal("41.000"),
            Decimal("50.000"),
            Decimal("36.000"),
            Decimal("44.000"),
        ),
        (
            "MCV",
            "Mean Corpuscular Volume",
            "Haematology",
            "fL",
            Decimal("80.000"),
            Decimal("100.000"),
            Decimal("80.000"),
            Decimal("100.000"),
        ),
        (
            "MCH",
            "Mean Corpuscular Haemoglobin",
            "Haematology",
            "pg",
            Decimal("27.000"),
            Decimal("33.000"),
            Decimal("27.000"),
            Decimal("33.000"),
        ),
        (
            "MCHC",
            "Mean Corpuscular Haemoglobin Concentration",
            "Haematology",
            "g/dL",
            Decimal("32.000"),
            Decimal("36.000"),
            Decimal("32.000"),
            Decimal("36.000"),
        ),
        (
            "WBC",
            "Total WBC Count",
            "Haematology",
            "10^3/uL",
            Decimal("4.000"),
            Decimal("11.000"),
            Decimal("4.000"),
            Decimal("11.000"),
        ),
        (
            "NEUT",
            "Neutrophils %",
            "Haematology",
            "%",
            Decimal("40.000"),
            Decimal("75.000"),
            Decimal("40.000"),
            Decimal("75.000"),
        ),
        (
            "LYMPH",
            "Lymphocytes %",
            "Haematology",
            "%",
            Decimal("20.000"),
            Decimal("45.000"),
            Decimal("20.000"),
            Decimal("45.000"),
        ),
        (
            "MONO",
            "Monocytes %",
            "Haematology",
            "%",
            Decimal("2.000"),
            Decimal("10.000"),
            Decimal("2.000"),
            Decimal("10.000"),
        ),
        (
            "EOS",
            "Eosinophils %",
            "Haematology",
            "%",
            Decimal("1.000"),
            Decimal("6.000"),
            Decimal("1.000"),
            Decimal("6.000"),
        ),
        (
            "PLT",
            "Platelet Count",
            "Haematology",
            "10^3/uL",
            Decimal("150.000"),
            Decimal("450.000"),
            Decimal("150.000"),
            Decimal("450.000"),
        ),
    ),
    "LFT": (
        (
            "ALT",
            "Alanine Aminotransferase",
            "Biochemistry",
            "U/L",
            Decimal("7.000"),
            Decimal("56.000"),
            Decimal("7.000"),
            Decimal("45.000"),
        ),
        (
            "AST",
            "Aspartate Aminotransferase",
            "Biochemistry",
            "U/L",
            Decimal("8.000"),
            Decimal("48.000"),
            Decimal("8.000"),
            Decimal("43.000"),
        ),
        (
            "ALP",
            "Alkaline Phosphatase",
            "Biochemistry",
            "U/L",
            Decimal("40.000"),
            Decimal("129.000"),
            Decimal("35.000"),
            Decimal("104.000"),
        ),
        (
            "GGT",
            "Gamma-Glutamyl Transferase",
            "Biochemistry",
            "U/L",
            Decimal("8.000"),
            Decimal("61.000"),
            Decimal("5.000"),
            Decimal("36.000"),
        ),
        (
            "BILT",
            "Bilirubin, Total",
            "Biochemistry",
            "mg/dL",
            Decimal("0.100"),
            Decimal("1.200"),
            Decimal("0.100"),
            Decimal("1.200"),
        ),
        (
            "BILD",
            "Bilirubin, Direct",
            "Biochemistry",
            "mg/dL",
            Decimal("0.000"),
            Decimal("0.300"),
            Decimal("0.000"),
            Decimal("0.300"),
        ),
        (
            "ALB",
            "Albumin",
            "Biochemistry",
            "g/dL",
            Decimal("3.500"),
            Decimal("5.000"),
            Decimal("3.500"),
            Decimal("5.000"),
        ),
        (
            "TP",
            "Total Protein",
            "Biochemistry",
            "g/dL",
            Decimal("6.000"),
            Decimal("8.300"),
            Decimal("6.000"),
            Decimal("8.300"),
        ),
    ),
    "RFT": (
        (
            "UREA",
            "Blood Urea",
            "Biochemistry",
            "mg/dL",
            Decimal("15.000"),
            Decimal("45.000"),
            Decimal("15.000"),
            Decimal("45.000"),
        ),
        (
            "CREAT",
            "Creatinine",
            "Biochemistry",
            "mg/dL",
            Decimal("0.700"),
            Decimal("1.300"),
            Decimal("0.600"),
            Decimal("1.100"),
        ),
        (
            "NA",
            "Sodium",
            "Biochemistry",
            "mmol/L",
            Decimal("135.000"),
            Decimal("145.000"),
            Decimal("135.000"),
            Decimal("145.000"),
        ),
        (
            "K",
            "Potassium",
            "Biochemistry",
            "mmol/L",
            Decimal("3.500"),
            Decimal("5.100"),
            Decimal("3.500"),
            Decimal("5.100"),
        ),
        (
            "CL",
            "Chloride",
            "Biochemistry",
            "mmol/L",
            Decimal("98.000"),
            Decimal("107.000"),
            Decimal("98.000"),
            Decimal("107.000"),
        ),
        (
            "CA",
            "Calcium (Total)",
            "Biochemistry",
            "mg/dL",
            Decimal("8.500"),
            Decimal("10.500"),
            Decimal("8.500"),
            Decimal("10.500"),
        ),
        (
            "URIC",
            "Uric Acid",
            "Biochemistry",
            "mg/dL",
            Decimal("3.400"),
            Decimal("7.000"),
            Decimal("2.400"),
            Decimal("6.000"),
        ),
    ),
    "LIPID": (
        (
            "CHOL",
            "Total Cholesterol",
            "Biochemistry",
            "mg/dL",
            Decimal("120.000"),
            Decimal("200.000"),
            Decimal("120.000"),
            Decimal("200.000"),
        ),
        (
            "TG",
            "Triglycerides",
            "Biochemistry",
            "mg/dL",
            Decimal("40.000"),
            Decimal("150.000"),
            Decimal("40.000"),
            Decimal("150.000"),
        ),
        (
            "HDL",
            "HDL Cholesterol",
            "Biochemistry",
            "mg/dL",
            Decimal("40.000"),
            Decimal("60.000"),
            Decimal("50.000"),
            Decimal("60.000"),
        ),
        (
            "LDL",
            "LDL Cholesterol (calculated)",
            "Biochemistry",
            "mg/dL",
            Decimal("50.000"),
            Decimal("100.000"),
            Decimal("50.000"),
            Decimal("100.000"),
        ),
        (
            "VLDL",
            "VLDL Cholesterol (calculated)",
            "Biochemistry",
            "mg/dL",
            Decimal("5.000"),
            Decimal("30.000"),
            Decimal("5.000"),
            Decimal("30.000"),
        ),
    ),
}

NOTIFICATION_TEMPLATE_SPECS: tuple[
    tuple[str, str, str, str | None, str, dict[str, Any]], ...
] = (
    # sample_collected
    (
        "sample_collected",
        "en",
        "email",
        "Sample Collected — {{ accession_id }}",
        (
            "Dear {{ patient_name }}, your sample {{ accession_id }} "
            "has been collected at {{ lab_name }}."
        ),
        {"variables": ["patient_name", "accession_id", "lab_name"]},
    ),
    (
        "sample_collected",
        "ur",
        "email",
        "سیمپل حاصل کر لیا گیا — {{ accession_id }}",
        (
            "محترم {{ patient_name }}، آپ کا سیمپل {{ accession_id }} "
            "{{ lab_name }} میں حاصل کر لیا گیا ہے۔"
        ),
        {"variables": ["patient_name", "accession_id", "lab_name"]},
    ),
    (
        "sample_collected",
        "en",
        "whatsapp",
        None,
        (
            "Hello {{ patient_name }}, your sample {{ accession_id }} "
            "has been collected at {{ lab_name }}."
        ),
        {"variables": ["patient_name", "accession_id", "lab_name"]},
    ),
    (
        "sample_collected",
        "ur",
        "whatsapp",
        None,
        (
            "محترم {{ patient_name }}، آپ کا سیمپل {{ accession_id }} "
            "{{ lab_name }} میں حاصل کر لیا گیا ہے۔"
        ),
        {"variables": ["patient_name", "accession_id", "lab_name"]},
    ),
    # report_ready
    (
        "report_ready",
        "en",
        "email",
        "Your Lab Report is Ready — {{ accession_id }}",
        (
            "Dear {{ patient_name }}, your report is ready. "
            "View it securely here: {{ patient_link }}"
        ),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    (
        "report_ready",
        "ur",
        "email",
        "آپ کی لیب رپورٹ تیار ہے — {{ accession_id }}",
        (
            "محترم {{ patient_name }}، آپ کی رپورٹ تیار ہے۔ "
            "یہاں دیکھیں: {{ patient_link }}"
        ),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    (
        "report_ready",
        "en",
        "whatsapp",
        None,
        (
            "Dear {{ patient_name }}, your report ({{ accession_id }}) "
            "is ready: {{ patient_link }}"
        ),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    (
        "report_ready",
        "ur",
        "whatsapp",
        None,
        (
            "محترم {{ patient_name }}، آپ کی رپورٹ ({{ accession_id }}) "
            "تیار ہے: {{ patient_link }}"
        ),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    # report_link_resend
    (
        "report_link_resend",
        "en",
        "email",
        "Updated Lab Report Link — {{ accession_id }}",
        (
            "Dear {{ patient_name }}, here is your updated report link: "
            "{{ patient_link }}"
        ),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    (
        "report_link_resend",
        "ur",
        "email",
        "رپورٹ کا نیا لنک — {{ accession_id }}",
        ("محترم {{ patient_name }}، آپ کی رپورٹ کا نیا لنک یہ ہے: {{ patient_link }}"),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    (
        "report_link_resend",
        "en",
        "whatsapp",
        None,
        (
            "Dear {{ patient_name }}, here is your report link "
            "({{ accession_id }}): {{ patient_link }}"
        ),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    (
        "report_link_resend",
        "ur",
        "whatsapp",
        None,
        (
            "محترم {{ patient_name }}، آپ کی رپورٹ کا لنک "
            "({{ accession_id }}): {{ patient_link }}"
        ),
        {"variables": ["patient_name", "accession_id", "patient_link", "lab_name"]},
    ),
    # settlement_ready
    (
        "settlement_ready",
        "en",
        "email",
        "Monthly Settlement Statement — {{ period }}",
        (
            "Dear {{ partner_name }}, please find attached your "
            "settlement statement for {{ period }}."
        ),
        {"variables": ["partner_name", "period", "lab_name"]},
    ),
    (
        "settlement_ready",
        "ur",
        "email",
        "ماہانہ سیٹلمنٹ اسٹیٹمنٹ — {{ period }}",
        (
            "محترم {{ partner_name }}، براہ کرم {{ period }} کی "
            "سیٹلمنٹ اسٹیٹمنٹ منسلک ملاحظہ فرمائیں۔"
        ),
        {"variables": ["partner_name", "period", "lab_name"]},
    ),
    (
        "settlement_ready",
        "en",
        "whatsapp",
        None,
        "Dear {{ partner_name }}, your settlement statement for {{ period }} is ready.",
        {"variables": ["partner_name", "period", "lab_name"]},
    ),
    (
        "settlement_ready",
        "ur",
        "whatsapp",
        None,
        "محترم {{ partner_name }}، {{ period }} کی سیٹلمنٹ اسٹیٹمنٹ تیار ہے۔",
        {"variables": ["partner_name", "period", "lab_name"]},
    ),
)


def _seed_reference_ranges_for_test(
    test_obj: Test,
    *,
    unit: str,
    m_low: Decimal,
    m_high: Decimal,
    f_low: Decimal,
    f_high: Decimal,
    effective_from: date,
) -> None:
    """
    Idempotently seed adult-M and adult-F reference_range rows (plus both-sex 'B'
    where M and F intervals are identical), starting at age_min_days = 6570
    (Doc 02 §16).
    """
    ReferenceRange.objects.get_or_create(
        test=test_obj,
        sex="M",
        age_min_days=ADULT_MIN_DAYS,
        age_max_days=None,
        effective_from=effective_from,
        defaults={
            "low": m_low,
            "high": m_high,
            "critical_low": None,
            "critical_high": None,
            "unit": unit,
            "effective_to": None,
        },
    )
    ReferenceRange.objects.get_or_create(
        test=test_obj,
        sex="F",
        age_min_days=ADULT_MIN_DAYS,
        age_max_days=None,
        effective_from=effective_from,
        defaults={
            "low": f_low,
            "high": f_high,
            "critical_low": None,
            "critical_high": None,
            "unit": unit,
            "effective_to": None,
        },
    )
    if m_low == f_low and m_high == f_high:
        ReferenceRange.objects.get_or_create(
            test=test_obj,
            sex="B",
            age_min_days=ADULT_MIN_DAYS,
            age_max_days=None,
            effective_from=effective_from,
            defaults={
                "low": m_low,
                "high": m_high,
                "critical_low": None,
                "critical_high": None,
                "unit": unit,
                "effective_to": None,
            },
        )


def seed_tenant_p6_data(tenant: Tenant) -> None:
    """
    Execute Step P-6 inside `tenant.schema_name` (Doc 02 §16, Doc 04 §5 P-6):
    1. Default branch (`HQ1` — Main Branch).
    2. Starter catalogue: 4 panels (`CBC`, `LFT`, `RFT`, `LIPID`) with all 32
       component tests linked via `PanelTest`, plus 5 standalone tests
       (`HBA1C`, `BSF`, `BSR`, `URE`, `TSH`), initial `TestPrice` rows,
       and adult `ReferenceRange` rows (`age_min_days=6570`).
    3. Bilingual (`en`, `ur`) `NotificationTemplate` rows for `sample_collected`,
       `report_ready`, `report_link_resend`, and `settlement_ready`.
    4. Strictly ZERO `RevenueShareRule` rows (A-10) and ZERO clinical/demo rows.
    """
    provisioning_date: date = (
        tenant.created_at.date() if tenant.created_at else date(2026, 1, 1)
    )
    provisioning_effective_dt = datetime(
        provisioning_date.year,
        provisioning_date.month,
        provisioning_date.day,
        0,
        0,
        0,
        tzinfo=UTC,
    )

    with schema_context(tenant.schema_name):
        # 1. Default branch (Doc 02 §16)
        Branch.objects.get_or_create(
            code="HQ1",
            defaults={
                "name": f"{tenant.name} — Main Branch",
                "address": "",
                "phone": "",
                "is_collection_centre": False,
                "result_entry_enabled": False,
            },
        )

        # 2a. Starter Panels + Component Tests + PanelTest + ReferenceRange + TestPrice
        for panel_code, panel_name, panel_price in STARTER_PANELS:
            panel_obj, _ = Panel.objects.get_or_create(
                code=panel_code,
                defaults={
                    "name": panel_name,
                    "is_active": True,
                },
            )
            TestPrice.objects.get_or_create(
                branch=None,
                test=None,
                panel=panel_obj,
                effective_from=provisioning_effective_dt,
                defaults={
                    "price": panel_price,
                    "effective_to": None,
                },
            )

            for (
                comp_code,
                comp_name,
                comp_cat,
                comp_unit,
                m_low,
                m_high,
                f_low,
                f_high,
            ) in PANEL_COMPONENT_TESTS[panel_code]:
                comp_test, _ = Test.objects.get_or_create(
                    code=comp_code,
                    defaults={
                        "name": comp_name,
                        "category": comp_cat,
                        "unit": comp_unit,
                        "is_active": True,
                    },
                )
                PanelTest.objects.get_or_create(
                    panel=panel_obj,
                    test=comp_test,
                )
                _seed_reference_ranges_for_test(
                    comp_test,
                    unit=comp_unit,
                    m_low=m_low,
                    m_high=m_high,
                    f_low=f_low,
                    f_high=f_high,
                    effective_from=provisioning_date,
                )

        # 2b. Standalone Starter Tests + TestPrice + ReferenceRange
        for (
            test_code,
            test_name,
            test_cat,
            test_unit,
            test_price,
            m_low,
            m_high,
            f_low,
            f_high,
        ) in STARTER_STANDALONE_TESTS:
            test_obj, _ = Test.objects.get_or_create(
                code=test_code,
                defaults={
                    "name": test_name,
                    "category": test_cat,
                    "unit": test_unit,
                    "is_active": True,
                },
            )
            TestPrice.objects.get_or_create(
                branch=None,
                test=test_obj,
                panel=None,
                effective_from=provisioning_effective_dt,
                defaults={
                    "price": test_price,
                    "effective_to": None,
                },
            )
            _seed_reference_ranges_for_test(
                test_obj,
                unit=test_unit,
                m_low=m_low,
                m_high=m_high,
                f_low=f_low,
                f_high=f_high,
                effective_from=provisioning_date,
            )

        # 3. Notification templates in English and Urdu (Doc 02 §5.9, §16)
        for (
            tpl_key,
            tpl_locale,
            tpl_channel,
            tpl_subject,
            tpl_body,
            tpl_schema,
        ) in NOTIFICATION_TEMPLATE_SPECS:
            NotificationTemplate.objects.get_or_create(
                key=tpl_key,
                locale=tpl_locale,
                channel=tpl_channel,
                defaults={
                    "subject": tpl_subject,
                    "body": tpl_body,
                    "template_context_schema": tpl_schema,
                },
            )


def seed_tenant_p7_settings(tenant: Tenant) -> None:
    """
    Execute Step P-7 inside `tenant.schema_name` (Doc 04 §5 P-7, §10.2):
    Insert default `tenant_setting` rows via `get_or_create` per key so re-runs
    never overwrite existing values or create duplicates.
    """
    default_settings: tuple[tuple[str, str], ...] = (
        ("billing_hold_enabled", "false"),
        ("report_default_language", "en"),
        ("report_link_validity_days", "7"),
        ("transfer_late_after_hours", "24"),
        ("brand_display_name", tenant.name),
        ("brand_accent_colour", "#0d9488"),
    )

    with schema_context(tenant.schema_name):
        for setting_key, setting_val in default_settings:
            TenantSetting.objects.get_or_create(
                key=setting_key,
                defaults={
                    "value": setting_val,
                    "updated_by": None,
                },
            )
