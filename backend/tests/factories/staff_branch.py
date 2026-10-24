import factory

from apps.accounts.models import StaffBranch
from tests.factories.base import TenantModelFactory
from tests.factories.branch import BranchFactory
from tests.factories.staff_user import StaffUserFactory


class StaffBranchFactory(TenantModelFactory):
    class Meta:
        model = StaffBranch

    staff_user = factory.SubFactory(StaffUserFactory)
    branch = factory.SubFactory(BranchFactory)
    is_primary = False
