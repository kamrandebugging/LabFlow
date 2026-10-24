"""Factory package for LabFlow test suites per Doc 09 §9.4.

Root exports the public-schema core factories (LAB-5) plus the LAB-4
test-harness fixture factories and domain model factories (KAN-45 / KAN-36).
"""

from tests.factories.base import (
    BaseTenantFixtureFactory,
    PublicModelFactory,
    TenantModelFactory,
)
from tests.factories.branch import BranchFactory
from tests.factories.core import (
    DomainFactory,
    PlanFactory,
    PlatformAuditFactory,
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)
from tests.factories.login_event import LoginEventFactory
from tests.factories.staff_branch import StaffBranchFactory
from tests.factories.staff_user import StaffUserFactory
from tests.factories.tenants import TenantFixtureFactory

__all__ = [
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
]
