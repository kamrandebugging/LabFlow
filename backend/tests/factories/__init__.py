"""Factory package for LabFlow test suites per Doc 09 §9.4.

Root exports the public-schema core factories (LAB-5) plus the LAB-4
test-harness fixture factories. Note: tests.factories.tenants.TenantFactory
remains the TenantFixtureFactory alias used by the LAB-4 harness; the root
TenantFactory is the real Tenant model factory from tests.factories.core.
"""

from tests.factories.base import (
    BaseTenantFixtureFactory,
    PublicModelFactory,
    TenantModelFactory,
)
from tests.factories.core import (
    DomainFactory,
    PlanFactory,
    PlatformAuditFactory,
    PlatformUserFactory,
    SubscriptionFactory,
    TenantFactory,
)
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
]
