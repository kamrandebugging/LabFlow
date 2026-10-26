import factory
from django.utils import timezone

from apps.results.models import CriticalNotification, Result, ResultApproval
from tests.factories.accounts import StaffUserFactory
from tests.factories.base import TenantModelFactory
from tests.factories.catalog import TestFactory
from tests.factories.samples import SampleFactory


class ResultFactory(TenantModelFactory):
    class Meta:
        model = Result

    sample = factory.SubFactory(SampleFactory)
    test = factory.SubFactory(TestFactory)
    value = "95.0"
    unit = "mg/dL"
    flag = Result.Flag.NORMAL
    status = Result.Status.ENTERED
    entered_by = factory.SubFactory(StaffUserFactory)


class ResultApprovalFactory(TenantModelFactory):
    class Meta:
        model = ResultApproval

    result = factory.SubFactory(ResultFactory)
    pathologist = factory.SubFactory(StaffUserFactory)
    decision = ResultApproval.Decision.APPROVED
    note = None
    range_override = False


class CriticalNotificationFactory(TenantModelFactory):
    class Meta:
        model = CriticalNotification

    result = factory.SubFactory(
        ResultFactory,
        flag=Result.Flag.CRITICAL,
    )
    notified_name = "Dr. Ayesha Khan"
    notified_at = factory.LazyFunction(timezone.now)
    read_back = True
    recorded_by = factory.SubFactory(StaffUserFactory)
