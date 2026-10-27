from __future__ import annotations

from datetime import date
from decimal import Decimal

import factory

from apps.partners.models import (
    ReferralPartner,
    RevenueShareRule,
    ShareLedgerEntry,
)
from tests.factories.base import TenantModelFactory
from tests.factories.billing import PaymentFactory
from tests.factories.branches import BranchFactory


class ReferralPartnerFactory(TenantModelFactory):
    class Meta:
        model = ReferralPartner

    name = factory.Sequence(lambda n: f"Dr. Referral Partner {n}")
    organisation = factory.Sequence(lambda n: f"Partner Clinic {n}")
    phone = factory.Sequence(lambda n: f"+92300111{n:04d}")
    email = factory.Sequence(lambda n: f"partner{n}@example.com")
    is_active = True
    deleted_at = None


class RevenueShareRuleFactory(TenantModelFactory):
    class Meta:
        model = RevenueShareRule

    referral_partner = factory.SubFactory(ReferralPartnerFactory)
    test_category = "Hematology"
    branch = factory.SubFactory(BranchFactory)
    percent = Decimal("20.00")
    effective_from = factory.LazyFunction(lambda: date(2026, 1, 1))
    effective_to = None


class ShareLedgerEntryFactory(TenantModelFactory):
    class Meta:
        model = ShareLedgerEntry

    payment = factory.SubFactory(PaymentFactory)
    referral_partner = factory.SubFactory(ReferralPartnerFactory)
    rule = factory.SubFactory(
        RevenueShareRuleFactory,
        referral_partner=factory.SelfAttribute("..referral_partner"),
    )
    amount = Decimal("200.00")
    percent_applied = Decimal("20.00")
    basis_amount = Decimal("1000.00")
    period = "2026-10"
