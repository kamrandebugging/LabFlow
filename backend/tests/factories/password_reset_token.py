from datetime import timedelta

import factory
from django.utils import timezone

from apps.accounts.models import PasswordResetToken
from tests.factories.base import TenantModelFactory
from tests.factories.staff_user import StaffUserFactory


class PasswordResetTokenFactory(TenantModelFactory):
    class Meta:
        model = PasswordResetToken

    staff_user = factory.SubFactory(StaffUserFactory)
    token_hash = factory.Sequence(lambda n: f"argon2id_hash_sample_token_{n}")
    purpose = PasswordResetToken.Purpose.PASSWORD_RESET
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=1))
    used_at = None

    class Params:
        email_verification = factory.Trait(
            purpose=PasswordResetToken.Purpose.EMAIL_VERIFICATION,
            expires_at=factory.LazyFunction(
                lambda: timezone.now() + timedelta(hours=24)
            ),
        )
        activation = factory.Trait(
            purpose=PasswordResetToken.Purpose.ACTIVATION,
            expires_at=factory.LazyFunction(
                lambda: timezone.now() + timedelta(hours=72)
            ),
        )
        used = factory.Trait(
            used_at=factory.LazyFunction(timezone.now),
        )
