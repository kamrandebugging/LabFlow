import factory

from apps.accounts.models import LoginEvent
from tests.factories.base import TenantModelFactory
from tests.factories.staff_user import StaffUserFactory


class LoginEventFactory(TenantModelFactory):
    class Meta:
        model = LoginEvent

    staff_user = factory.SubFactory(StaffUserFactory)
    email_attempted = factory.LazyAttribute(
        lambda o: o.staff_user.email if o.staff_user else "unknown@labflow.app"
    )
    success = True
    ip = "192.168.1.1"
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

    class Params:
        failed = factory.Trait(
            staff_user=None,
            email_attempted="invalid@labflow.app",
            success=False,
        )
