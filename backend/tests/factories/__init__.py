"""Factory package for LabFlow test suites per Doc 09 §9.4.

Root exports the public-schema core factories (LAB-5) plus the LAB-4
test-harness fixture factories and domain model factories (KAN-45 / KAN-36).
"""

from __future__ import annotations

from tests.factories.audit_log import AuditLogFactory
from tests.factories.automation import WebhookDeliveryFactory
from tests.factories.base import (
    BaseTenantFixtureFactory,
    PublicModelFactory,
    TenantModelFactory,
)
from tests.factories.billing import (
    InvoiceFactory,
    InvoiceItemFactory,
    PaymentFactory,
)
from tests.factories.branch import BranchFactory
from tests.factories.catalog import (
    PanelFactory,
    PanelTestFactory,
    ReferenceRangeFactory,
    TestFactory,
    TestPriceFactory,
)
from tests.factories.core import (
    DomainFactory,
    PlanFactory,
    PlatformAuditFactory,
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)
from tests.factories.login_event import LoginEventFactory
from tests.factories.notifications import (
    NotificationFactory,
    NotificationTemplateFactory,
)
from tests.factories.partners import (
    ReferralPartnerFactory,
    RevenueShareRuleFactory,
    SettlementFactory,
    SettlementLineFactory,
    ShareLedgerEntryFactory,
)
from tests.factories.password_reset_token import PasswordResetTokenFactory
from tests.factories.patients import (
    PatientConsentFactory,
    PatientContactFactory,
    PatientFactory,
)
from tests.factories.reports import (
    ReportAccessTokenFactory,
    ReportDeliveryFactory,
    ReportFactory,
    ReportVersionFactory,
)
from tests.factories.results import (
    CriticalNotificationFactory,
    ResultApprovalFactory,
    ResultFactory,
)
from tests.factories.samples import (
    SampleEventFactory,
    SampleFactory,
    SampleTestFactory,
    SampleTransferFactory,
)
from tests.factories.staff_branch import StaffBranchFactory
from tests.factories.staff_user import StaffUserFactory
from tests.factories.tenant_setting import TenantSettingFactory
from tests.factories.tenants import TenantFixtureFactory

__all__ = [
    "AuditLogFactory",
    "BaseTenantFixtureFactory",
    "BranchFactory",
    "CriticalNotificationFactory",
    "DomainFactory",
    "InvoiceFactory",
    "InvoiceItemFactory",
    "LoginEventFactory",
    "NotificationFactory",
    "NotificationTemplateFactory",
    "PanelFactory",
    "PanelTestFactory",
    "PasswordResetTokenFactory",
    "PatientConsentFactory",
    "PatientContactFactory",
    "PatientFactory",
    "PaymentFactory",
    "PlanFactory",
    "PlatformAuditFactory",
    "PlatformUserFactory",
    "PublicModelFactory",
    "ReferenceRangeFactory",
    "ReferralPartnerFactory",
    "ReportAccessTokenFactory",
    "ReportDeliveryFactory",
    "ReportFactory",
    "ReportVersionFactory",
    "ResultApprovalFactory",
    "ResultFactory",
    "RevenueShareRuleFactory",
    "SampleEventFactory",
    "SampleFactory",
    "SampleTestFactory",
    "SampleTransferFactory",
    "SettlementFactory",
    "SettlementLineFactory",
    "ShareLedgerEntryFactory",
    "StaffBranchFactory",
    "StaffUserFactory",
    "SubscriptionFactory",
    "TenantFactory",
    "TenantFixtureFactory",
    "TenantModelFactory",
    "TenantSettingFactory",
    "TestFactory",
    "TestPriceFactory",
    "WebhookDeliveryFactory",
]
