"""Factory package for LabFlow test suites per Doc 09 §9.4.

Root exports the public-schema core factories (LAB-5) plus the LAB-4
test-harness fixture factories and domain model factories (KAN-45 / KAN-36).
"""

from tests.factories.audit_log import AuditLogFactory
from tests.factories.base import (
    BaseTenantFixtureFactory,
    PublicModelFactory,
    TenantModelFactory,
)
from tests.factories.branch import BranchFactory
from tests.factories.catalog import (
    PanelFactory,
    PanelTestFactory,
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
from tests.factories.password_reset_token import PasswordResetTokenFactory
from tests.factories.patients import (
    PatientConsentFactory,
    PatientContactFactory,
    PatientFactory,
)
from tests.factories.staff_branch import StaffBranchFactory
from tests.factories.staff_user import StaffUserFactory
from tests.factories.tenant_setting import TenantSettingFactory
from tests.factories.tenants import TenantFixtureFactory

__all__ = [
    "AuditLogFactory",
    "BaseTenantFixtureFactory",
    "PublicModelFactory",
    "TenantModelFactory",
    "TenantFixtureFactory",
    "TenantFactory",
    "DomainFactory",
    "PlanFactory",
    "SubscriptionFactory",
    "PlatformUserFactory",
    "PlatformAuditFactory",
    "BranchFactory",
    "StaffUserFactory",
    "StaffBranchFactory",
    "LoginEventFactory",
    "PasswordResetTokenFactory",
    "TenantSettingFactory",
    "PatientFactory",
    "PatientContactFactory",
    "PatientConsentFactory",
    "TestFactory",
    "PanelFactory",
    "PanelTestFactory",
    "TestPriceFactory",
]
