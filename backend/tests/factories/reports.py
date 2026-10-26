from datetime import timedelta

import factory
from django.utils import timezone

from apps.reports.models import (
    Report,
    ReportAccessToken,
    ReportDelivery,
    ReportVersion,
)
from tests.factories.accounts import StaffUserFactory
from tests.factories.base import TenantModelFactory
from tests.factories.samples import SampleFactory


class ReportFactory(TenantModelFactory):
    class Meta:
        model = Report

    sample = factory.SubFactory(SampleFactory)
    status = Report.Status.DRAFT
    current_version = 0
    finalised_at = None


class ReportVersionFactory(TenantModelFactory):
    class Meta:
        model = ReportVersion

    report = factory.SubFactory(ReportFactory)
    version = factory.Sequence(lambda n: n + 1)
    pdf_key = factory.LazyAttribute(lambda o: f"reports/{o.report.id}/{o.version}.pdf")
    generated_by = factory.SubFactory(StaffUserFactory)


class ReportDeliveryFactory(TenantModelFactory):
    class Meta:
        model = ReportDelivery

    report = factory.SubFactory(ReportFactory)
    channel = ReportDelivery.Channel.EMAIL
    status = ReportDelivery.Status.PENDING
    whatsapp_url = None
    attempts = 0
    next_attempt_at = None
    last_error = None


class ReportAccessTokenFactory(TenantModelFactory):
    class Meta:
        model = ReportAccessToken

    report = factory.SubFactory(ReportFactory)
    token_hash = factory.Sequence(
        lambda n: f"$argon2id$v=19$m=65536,t=3,p=4$salt{n:06d}$hash{n:06d}"
    )
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    revoked_at = None
    last_accessed_at = None
