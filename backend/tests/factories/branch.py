import factory

from apps.branches.models import Branch
from tests.factories.base import TenantModelFactory


class BranchFactory(TenantModelFactory):
    class Meta:
        model = Branch

    code = factory.Sequence(lambda n: f"B{n % 90 + 10:02d}")
    name = factory.Sequence(lambda n: f"Branch {n}")
    address = factory.Faker("address")
    phone = factory.Sequence(lambda n: f"+92300{n % 10000000:07d}")
    is_collection_centre = False
    result_entry_enabled = False
    deleted_at = None
