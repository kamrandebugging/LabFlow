"""Public schema models: Tenant, Domain, Plan, Subscription per Doc 02 §4.1."""

import uuid
from decimal import Decimal

from django.contrib.postgres.functions import RandomUUID
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
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


class Plan(models.Model):
    """Platform pricing tier for tenant subscriptions (Doc 02 §4.1)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique tier name, e.g. Starter, Professional",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="PKR per month (Doc 01 ADR-010)",
    )
    max_branches = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum branches permitted; NULL denotes unlimited",
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Retired plans remain active for existing subscriptions but block new ones"
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "plan"
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=Decimal("0.00")),
                name="chk_plan_price_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (PKR {self.price})"


class Subscription(models.Model):
    """Tenant subscription contract to a platform plan (Doc 02 §4.1)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        db_column="tenant_id",
        db_index=False,
    )
    plan = models.ForeignKey(
        "core.Plan",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        db_column="plan_id",
        db_index=False,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        help_text="Subscription lifecycle status (Doc 02 §4.1)",
    )
    starts_at = models.DateTimeField(
        help_text="Start timestamp of the subscription period",
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End timestamp of the subscription; NULL while open-ended",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription"
        indexes = [
            models.Index(fields=["tenant"], name="idx_subscription_tenant_id"),
            models.Index(fields=["plan"], name="idx_subscription_plan_id"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=Q(status="active"),
                name="uq_subscription_one_active_per_tenant",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(ends_at__gt=F("starts_at")),
                name="chk_subscription_ends_at_gt_starts_at",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.slug} -> {self.plan.name} ({self.status})"
