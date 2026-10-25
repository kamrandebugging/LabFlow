from datetime import date

import factory
from django.utils import timezone

from apps.patients.models import Patient, PatientConsent, PatientContact
from tests.factories.accounts import StaffUserFactory
from tests.factories.base import TenantModelFactory
from tests.factories.branches import BranchFactory


class PatientFactory(TenantModelFactory):
    class Meta:
        model = Patient

    branch = factory.SubFactory(BranchFactory)
    mrn = factory.Sequence(lambda n: f"MRN-M01-{n + 1:06d}")
    name = factory.Sequence(lambda n: f"Test Patient {n + 1:04d}")
    phone = factory.Sequence(lambda n: f"0300{n + 1:07d}")
    sex = Patient.Sex.MALE
    date_of_birth = date(1990, 1, 15)
    deleted_at = None


class PatientContactFactory(TenantModelFactory):
    class Meta:
        model = PatientContact

    patient = factory.SubFactory(PatientFactory)
    kind = PatientContact.Kind.PHONE
    value = factory.Sequence(lambda n: f"0321{n + 1:07d}")
    is_primary = True


class PatientConsentFactory(TenantModelFactory):
    class Meta:
        model = PatientConsent

    patient = factory.SubFactory(PatientFactory)
    channel = PatientConsent.Channel.WHATSAPP
    granted_at = factory.LazyFunction(timezone.now)
    granted_by = factory.SubFactory(StaffUserFactory)
    revoked_at = None
