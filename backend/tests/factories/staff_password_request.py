import factory

from apps.accounts.models import StaffPasswordResetRequest
from tests.factories.base import TenantModelFactory


class StaffPasswordResetRequestFactory(TenantModelFactory):
    class Meta:
        model = StaffPasswordResetRequest

    email = factory.Sequence(lambda n: f"forgot_{n}@labflow.app")
    display_name = "Forgot Password Staff"
    status = StaffPasswordResetRequest.Status.PENDING
    resolved_at = None
    resolved_by = None
