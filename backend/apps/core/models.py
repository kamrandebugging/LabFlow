"""Public schema models: Tenant and Domain per Doc 02 §4.1."""

import uuid

from django.contrib.postgres.functions import RandomUUID
from django.core.validators import RegexValidator
from django.db import models
from django_tenants.models import DomainMixin, TenantMixin

slug_validator = RegexValidator(
    regex=r"^[a-z][a-z0-9]{2,29}$",
    message=(
        "Slug must be 3-30 lowercase alphanumeric characters, starting with a letter."
    ),
)


class Tenant(TenantMixin):
    """A diagnostic laboratory or chain on the platform (Doc 02 §4.1)."""

    class Status(models.TextChoices):
        PROVISIONING = "provisioning", "Provisioning"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    slug = models.CharField(
        max_length=30,
        validators=[slug_validator],
        help_text="Subdomain and schema suffix: tenant_<slug>",
    )
    name = models.CharField(
        max_length=255,
        help_text="Display name of the lab",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROVISIONING,
        help_text="Lifecycle state (application-enforced only)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True
    auto_drop_schema = True

    class Meta:
        db_table = "tenant"
        constraints = [
            models.UniqueConstraint(fields=["slug"], name="uq_tenant_slug"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class Domain(DomainMixin):
    """Hostname mapping for tenant routing and TLS ask endpoint (Doc 02 §4.1)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    domain = models.CharField(
        max_length=253,
        help_text="Fully qualified domain name, e.g. citylab.labflow.app",
    )
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="domains",
        db_column="tenant_id",
        db_index=False,
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "domain"
        constraints = [
            models.UniqueConstraint(fields=["domain"], name="uq_domain_domain"),
        ]
        indexes = [
            models.Index(fields=["tenant"], name="idx_domain_tenant_id"),
        ]

    def __str__(self) -> str:
        return self.domain
