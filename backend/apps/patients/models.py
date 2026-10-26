import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models.functions import Now


class Patient(models.Model):
    """A person registered for testing at this lab (Doc 02 §5.2).

    Lives strictly in each tenant schema (TENANT_APPS).
    """

    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.PROTECT,
        related_name="patients",
        db_column="branch_id",
        db_index=False,
    )
    mrn = models.TextField()
    name = models.TextField()
    phone = models.TextField()
    sex = models.TextField(choices=Sex.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "patient"
        constraints = [
            models.UniqueConstraint(
                fields=["mrn"],
                name="uq_patient_mrn",
            ),
        ]
        indexes = [
            models.Index(
                fields=["branch"],
                name="idx_patient_branch_id",
            ),
            GinIndex(
                fields=["name"],
                name="idx_patient_name_trgm",
                opclasses=["gin_trgm_ops"],
            ),
            GinIndex(
                fields=["phone"],
                name="idx_patient_phone_trgm",
                opclasses=["gin_trgm_ops"],
            ),
            models.Index(
                fields=["deleted_at"],
                name="idx_patient_deleted_at",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.mrn} - {self.name}"


class PatientContact(models.Model):
    """Additional contact channels (email, alternate phone, WhatsApp number)

    for a patient without widening the patient table (Doc 02 §5.2).
    """

    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        WHATSAPP = "whatsapp", "WhatsApp"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="contacts",
        db_column="patient_id",
        db_index=False,
    )
    kind = models.TextField(choices=Kind.choices)
    value = models.TextField()
    is_primary = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "patient_contact"
        indexes = [
            models.Index(
                fields=["patient"],
                name="idx_patient_contact_patient_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.patient_id} ({self.kind}: {self.value})"


class PatientConsent(models.Model):
    """Record of consent for report delivery by email / WhatsApp link (Doc 02 §5.2).

    Has created_at only; revocation is recorded via revoked_at timestamp.
    """

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="consents",
        db_column="patient_id",
        db_index=False,
    )
    channel = models.TextField(choices=Channel.choices)
    granted_at = models.DateTimeField()
    granted_by = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recorded_patient_consents",
        db_column="granted_by",
        db_index=False,
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_default=Now(),
    )

    class Meta:
        db_table = "patient_consent"
        indexes = [
            models.Index(
                fields=["patient"],
                name="idx_patient_consent_patient_id",
            ),
            models.Index(
                fields=["granted_by"],
                name="idx_patient_consent_granted_by",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.patient_id} ({self.channel})"
