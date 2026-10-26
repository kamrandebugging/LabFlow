import factory
from django.utils import timezone

from apps.samples.models import Sample, SampleEvent, SampleTest, SampleTransfer
from tests.factories.accounts import StaffUserFactory
from tests.factories.base import TenantModelFactory
from tests.factories.billing import InvoiceFactory, InvoiceItemFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory


class SampleFactory(TenantModelFactory):
    class Meta:
        model = Sample

    invoice = factory.SubFactory(InvoiceFactory)
    branch = factory.SubFactory(BranchFactory)
    accession_id = factory.Sequence(lambda n: f"CIT20261020{n + 1:06d}")
    status = Sample.Status.COLLECTED
    collected_at = factory.LazyFunction(timezone.now)
    collected_by = factory.SubFactory(StaffUserFactory)
    rejection_reason_code = None
    rejection_note = None


class SampleTestFactory(TenantModelFactory):
    class Meta:
        model = SampleTest

    sample = factory.SubFactory(SampleFactory)
    invoice_item = factory.SubFactory(InvoiceItemFactory)
    test = factory.SubFactory(TestFactory)


class SampleEventFactory(TenantModelFactory):
    class Meta:
        model = SampleEvent

    sample = factory.SubFactory(SampleFactory)
    event = SampleEvent.EventType.COLLECTED
    actor = factory.SubFactory(StaffUserFactory)
    branch = factory.SubFactory(BranchFactory)
    note = None


class SampleTransferFactory(TenantModelFactory):
    class Meta:
        model = SampleTransfer

    sample = factory.SubFactory(SampleFactory)
    from_branch = factory.SubFactory(BranchFactory)
    to_branch = factory.SubFactory(BranchFactory)
    transferred_by = factory.SubFactory(StaffUserFactory)
    received_by = None
    status = SampleTransfer.Status.OPEN
    dispatched_at = factory.LazyFunction(timezone.now)
    received_at = None
