from datetime import date
from decimal import Decimal

import factory
from django.utils import timezone

from apps.catalog.models import Panel, PanelTest, ReferenceRange, Test, TestPrice
from tests.factories.base import TenantModelFactory


class TestFactory(TenantModelFactory):
    __test__ = False

    class Meta:
        model = Test

    code = factory.Sequence(lambda n: f"TST{n + 1:04d}")
    name = factory.Sequence(lambda n: f"Diagnostic Test {n + 1:04d}")
    category = "biochemistry"
    unit = "mg/dL"
    is_active = True


class PanelFactory(TenantModelFactory):
    class Meta:
        model = Panel

    code = factory.Sequence(lambda n: f"PNL{n + 1:04d}")
    name = factory.Sequence(lambda n: f"Diagnostic Panel {n + 1:04d}")
    is_active = True


class PanelTestFactory(TenantModelFactory):
    class Meta:
        model = PanelTest

    panel = factory.SubFactory(PanelFactory)
    test = factory.SubFactory(TestFactory)


class TestPriceFactory(TenantModelFactory):
    __test__ = False

    class Meta:
        model = TestPrice

    branch = None
    test = factory.SubFactory(TestFactory)
    panel = None
    price = Decimal("1500.00")
    effective_from = factory.LazyFunction(timezone.now)
    effective_to = None


class ReferenceRangeFactory(TenantModelFactory):
    class Meta:
        model = ReferenceRange

    test = factory.SubFactory(TestFactory)
    sex = ReferenceRange.Sex.BOTH
    age_min_days = 6570
    age_max_days = None
    low = Decimal("70.000")
    high = Decimal("110.000")
    critical_low = Decimal("40.000")
    critical_high = Decimal("400.000")
    unit = "mg/dL"
    effective_from = date(2026, 1, 1)
    effective_to = None
