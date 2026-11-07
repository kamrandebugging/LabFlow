"""Public schema models: Tenant, Domain, Plan, Subscription, PlatformUser,
PlatformAudit per Doc 02 §4.1.
"""

import uuid
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.functions import RandomUUID
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
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
    branch_count = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Active (non-closed) branch counter mirrored from the tenant "
            "schema by BranchService (Doc 04 TP-4)."
        ),
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Primary facility city",
    )
    province = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Primary facility province/region",
    )
    owner_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Primary administrator / medical director name",
    )
    owner_email = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Primary administrator email address",
    )
    owner_phone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Primary contact phone / WhatsApp",
    )
    staff_seats_limit = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum allowed staff seats; NULL denotes unlimited",
    )
    staff_count = models.PositiveIntegerField(
        default=1,
        help_text="Current staff count",
    )
    temp_password = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Initial temporary credential issued during provisioning",
    )
    temp_password_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Expiry timestamp for temporary credential (24h)",
    )
    enabled_roles = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
        help_text="List of roles enabled during provisioning",
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
    max_staff = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum staff permitted; NULL denotes unlimited",
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
    billing_cycle = models.CharField(
        max_length=20,
        default="monthly",
        help_text="Billing cadence: monthly, annual, lifetime",
    )
    next_due = models.DateField(
        null=True,
        blank=True,
        help_text="Next payment renewal due date",
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


class PlatformUser(models.Model):
    """Super Admin operator account in public schema (Doc 02 §4.1)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    email = models.EmailField(
        max_length=254,
        unique=True,
        help_text="Login identifier for platform operators",
    )
    password_hash = models.CharField(
        max_length=255,
        help_text="argon2 password hash",
    )
    totp_secret_encrypted = models.TextField(  # noqa: DJ001
        null=True,
        blank=True,
        help_text="Encrypted TOTP secret; NULL until 2FA enrolment",
    )
    totp_backup_codes_hash = ArrayField(
        models.TextField(),
        null=True,
        blank=True,
        help_text="Array of argon2 hashes for single-use backup codes",
    )
    totp_enabled = models.BooleanField(
        default=False,
        help_text="TOTP 2FA required for Super Admin roles per Doc 01 §14",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Deactivate account rather than soft-deleting",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_user"

    def __str__(self) -> str:
        return self.email

    def set_password(self, raw_password: str) -> None:
        """Hash and assign password using Django's argon2 hasher."""
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify candidate raw password against password_hash."""
        return check_password(raw_password, self.password_hash)


class PlatformAudit(models.Model):
    """Append-only audit trail of Super Admin actions (Doc 02 §4.1)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    actor_id = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "Plain UUID of platform_user; NULL for system events (no FK per Doc 02 §17)"
        ),
    )
    action = models.CharField(
        max_length=100,
        help_text="Action name, e.g. tenant.created, tenant.suspended",
    )
    entity_type = models.CharField(
        max_length=100,
        help_text="Polymorphic target entity type, e.g. tenant, plan",
    )
    entity_id = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "Polymorphic target entity UUID (no FK); NULL when the subject "
            "could not be resolved, e.g. a failed login for an unknown email"
        ),
    )
    before_jsonb = models.JSONField(
        null=True,
        blank=True,
        help_text="Changed fields state prior to mutation",
    )
    after_jsonb = models.JSONField(
        null=True,
        blank=True,
        help_text="Changed fields state after mutation",
    )
    ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP address",
    )
    user_agent = models.TextField(  # noqa: DJ001
        null=True,
        blank=True,
        help_text="Client User-Agent header",
    )
    at = models.DateTimeField(
        auto_now_add=True,
        help_text="Creation timestamp; append-only table without updated_at",
    )

    class Meta:
        db_table = "platform_audit"
        indexes = [
            models.Index(fields=["at"], name="idx_platform_audit_at"),
            models.Index(
                fields=["entity_type", "entity_id"],
                name="idx_platform_audit_entity",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} on {self.entity_type}:{self.entity_id} at {self.at}"


class PlatformPasswordResetToken(models.Model):
    """Single-use password reset token for a PlatformUser (Doc 08 §4.5).

    Only the argon2id hash of the 32-byte raw token is stored. Tokens live in
    the public schema because platform operators are global, not tenant-scoped.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    platform_user = models.ForeignKey(
        "core.PlatformUser",
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
        db_column="platform_user_id",
    )
    token_hash = models.CharField(max_length=255, help_text="argon2 token hash")
    expires_at = models.DateTimeField(help_text="Hard expiry timestamp")
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Consumption timestamp; NULL while still usable",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_password_reset_token"
        indexes = [
            models.Index(
                fields=["platform_user", "used_at"],
                name="idx_platform_reset_user_used",
            ),
        ]

    def __str__(self) -> str:
        return f"Platform reset token for {self.platform_user_id}"


class SubscriptionPayment(models.Model):
    """Payment record for a tenant subscription (Phase 2 Mark Paid)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="payments",
        db_column="tenant_id",
    )
    subscription = models.ForeignKey(
        "core.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        db_column="subscription_id",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Settled amount in PKR",
    )
    method = models.CharField(
        max_length=50,
        help_text="Payment method: Bank Transfer, Easypaisa, JazzCash",
    )
    reference = models.CharField(
        max_length=100,
        help_text="Bank transaction or gateway reference number",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Settlement reason or operator notes",
    )
    paid_date = models.DateField(
        default=timezone.now,
        help_text="Date funds were received",
    )
    recorded_by = models.ForeignKey(
        "core.PlatformUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
        db_column="recorded_by_id",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscription_payment"
        indexes = [
            models.Index(fields=["tenant"], name="idx_sub_payment_tenant"),
            models.Index(fields=["subscription"], name="idx_sub_payment_sub"),
            models.Index(fields=["paid_date"], name="idx_sub_payment_paid_date"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.slug} - PKR {self.amount} via {self.method}"


class TenantFeatureFlag(models.Model):
    """Per-lab enterprise feature scope toggles (Doc 10)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="feature_flags",
        db_column="tenant_id",
    )
    flag_key = models.CharField(
        max_length=100,
        help_text="Feature flag identifier: referral_partners, settlements, etc.",
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Whether this enterprise feature scope is unlocked",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_feature_flag"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "flag_key"],
                name="uq_tenant_feature_flag",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant"], name="idx_tenant_feature_flag_t"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.slug}:{self.flag_key} = {self.enabled}"


class DemoRequest(models.Model):
    """Prospective laboratory demo inquiry and conversion lifecycle (Doc 16/17)."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        DEMO_DONE = "demo_done", "Demo Done"
        CONVERTED = "converted", "Converted"
        LOST = "lost", "Lost"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    lab_name = models.CharField(max_length=255, help_text="Facility display name")
    contact_person = models.CharField(
        max_length=255, help_text="Primary director/doctor"
    )
    whatsapp = models.CharField(max_length=50, help_text="Direct mobile / WhatsApp")
    message = models.TextField(
        blank=True, default="", help_text="Original inquiry text"
    )
    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.NEW,
        help_text="Commercial lead qualification status",
    )
    notes = models.TextField(blank=True, default="", help_text="Internal account notes")
    requested_at = models.DateTimeField(auto_now_add=True)
    converted_tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demo_requests",
        db_column="converted_tenant_id",
    )

    class Meta:
        db_table = "demo_request"
        indexes = [
            models.Index(fields=["status"], name="idx_demo_req_status"),
            models.Index(fields=["requested_at"], name="idx_demo_req_requested_at"),
            models.Index(fields=["converted_tenant"], name="idx_demo_req_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.lab_name} ({self.contact_person}) - {self.status}"


class PlatformSetting(models.Model):
    """Global commercial and operational configuration (Doc 15)."""

    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "core.PlatformUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="updated_by_id",
    )

    class Meta:
        db_table = "platform_setting"

    def __str__(self) -> str:
        return self.key


class PlatformUserInvitation(models.Model):
    """Pending platform operator invitations."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        db_default=RandomUUID(),
        editable=False,
    )
    email = models.EmailField(max_length=254, unique=True)
    role = models.CharField(max_length=50, default="support")
    invited_by = models.ForeignKey(
        "core.PlatformUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="invited_by_id",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_user_invitation"

    def __str__(self) -> str:
        return f"{self.email} ({self.role}) - {self.status}"


# Re-export TenantSetting for core/tenancy namespace access
from apps.accounts.models import TenantSetting  # noqa: E402

__all__ = [
    "Tenant",
    "Domain",
    "Plan",
    "Subscription",
    "SubscriptionPayment",
    "TenantFeatureFlag",
    "DemoRequest",
    "PlatformSetting",
    "PlatformUserInvitation",
    "PlatformUser",
    "PlatformAudit",
    "PlatformPasswordResetToken",
    "TenantSetting",
]
