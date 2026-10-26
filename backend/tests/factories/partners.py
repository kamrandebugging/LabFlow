import factory

from apps.partners.models import ReferralPartner
from tests.factories.base import TenantModelFactory


class ReferralPartnerFactory(TenantModelFactory):
    class Meta:
        model = ReferralPartner

    name = factory.Sequence(lambda n: f"Dr. Referral Partner {n + 1:04d}")
    organisation = "City Clinic"
    phone = factory.Sequence(lambda n: f"0333{n + 1:07d}")
    email = factory.Sequence(lambda n: f"partner{n + 1:04d}@example.com")
    is_active = True
    deleted_at = None
