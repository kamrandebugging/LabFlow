import factory

from apps.accounts.models import TenantSetting
from tests.factories.base import TenantModelFactory
from tests.factories.staff_user import StaffUserFactory


class TenantSettingFactory(TenantModelFactory):
    class Meta:
        model = TenantSetting

    key = factory.Sequence(lambda n: f"setting_key_{n}")
    value = "setting_default_value"
    updated_by = factory.SubFactory(StaffUserFactory)
