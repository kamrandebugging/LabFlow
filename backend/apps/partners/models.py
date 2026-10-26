import uuid

from django.db import models
from django.db.models.functions import Now


class ReferralPartner(models.Model):
    """A referring doctor or facility (Doc 02 §5.8).

    Record only — no login in v1; receives a monthly statement PDF.
    Soft-deleted via deleted_at so historical invoices and ledger rows keep FKs.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=models.Func(function="gen_random_uuid"),
        editable=False,
    )
    name = models.TextField()
    organisation = models.TextField(null=True, blank=True)  # noqa: DJ001
    phone = models.TextField(null=True, blank=True)  # noqa: DJ001
    email = models.TextField(null=True, blank=True)  # noqa: DJ001
    is_active = models.BooleanField(default=True, db_default=True)
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
        db_table = "referral_partner"
        indexes = [
            models.Index(
                fields=["deleted_at"],
                name="idx_referral_partner_deleted_at",
            ),
        ]

    def __str__(self) -> str:
        return self.name
