import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.branches.models import Branch


class Role(models.TextChoices):
    OWNER = "owner", "Lab Owner"
    MANAGER = "manager", "Branch Manager"
    RECEPTION = "reception", "Receptionist / Collection Staff"
    TECHNICIAN = "technician", "Lab Technician"
    PATHOLOGIST = "pathologist", "Pathologist"


class StaffUser(models.Model):
    """Doc 02 §5.1: Staff accounts inside this tenant schema only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_users",
        db_column="branch_id",
    )
    role = models.CharField(max_length=50, choices=Role.choices)
    email = models.EmailField(max_length=255)
    password_hash = models.CharField(max_length=255)
    totp_secret_encrypted = models.TextField(null=True, blank=True)  # noqa: DJ001
    totp_backup_codes_hash = ArrayField(
        models.TextField(),
        null=True,
        blank=True,
    )
    totp_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "staff_user"
        constraints = [
            models.UniqueConstraint(fields=["email"], name="uq_staff_user_email"),
        ]
        indexes = [
            models.Index(fields=["branch"], name="idx_staff_user_branch_id"),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.role})"

    @property
    def is_authenticated(self) -> bool:
        """DRF and Django auth compatibility."""
        return True

    @property
    def is_anonymous(self) -> bool:
        """DRF and Django auth compatibility."""
        return False


class StaffBranch(models.Model):
    """Doc 02 §5.1: Join table linking staff_user and branch with composite primary key.

    No surrogate id column.
    """

    pk = models.CompositePrimaryKey("staff_user_id", "branch_id")
    staff_user = models.ForeignKey(
        StaffUser,
        on_delete=models.CASCADE,
        db_column="staff_user_id",
        related_name="staff_branches",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        db_column="branch_id",
        related_name="staff_branches",
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff_branch"
        indexes = [
            models.Index(fields=["staff_user"], name="idx_staff_branch_staff_user_id"),
            models.Index(fields=["branch"], name="idx_staff_branch_branch_id"),
        ]

    def __str__(self) -> str:
        return (
            f"StaffBranch(staff_user={self.staff_user_id}, "
            f"branch={self.branch_id}, primary={self.is_primary})"
        )


class LoginEvent(models.Model):
    """Doc 02 §5.11: Append-shaped record of staff sign-in attempts for security

    audit & throttles.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_user = models.ForeignKey(
        StaffUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="login_events",
        db_column="staff_user_id",
    )
    email_attempted = models.CharField(max_length=255)
    success = models.BooleanField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "login_event"
        indexes = [
            models.Index(fields=["staff_user"], name="idx_login_event_staff_user_id"),
            models.Index(fields=["created_at"], name="idx_login_event_created_at"),
            models.Index(
                fields=["email_attempted", "created_at"],
                name="idx_login_event_email_created",
            ),
            models.Index(
                fields=["ip", "created_at"], name="idx_login_event_ip_created"
            ),
        ]

    def __str__(self) -> str:
        status_label = "SUCCESS" if self.success else "FAILED"
        return f"LoginEvent({self.email_attempted}, {status_label}, {self.created_at})"


class PasswordResetToken(models.Model):
    """Doc 02 §5.11: Hashed, single-use, expiring tokens for password reset,

    email verification, and activation.
    """

    class Purpose(models.TextChoices):
        PASSWORD_RESET = "password_reset", "Password Reset"
        EMAIL_VERIFICATION = "email_verification", "Email Verification"
        ACTIVATION = "activation", "Activation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_user = models.ForeignKey(
        StaffUser,
        on_delete=models.CASCADE,
        db_column="staff_user_id",
        related_name="password_reset_tokens",
    )
    token_hash = models.CharField(max_length=255)
    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.PASSWORD_RESET,
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "password_reset_token"
        constraints = [
            models.UniqueConstraint(
                fields=["token_hash"],
                name="uq_password_reset_token_token_hash",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    purpose__in=[
                        "password_reset",
                        "email_verification",
                        "activation",
                    ]
                ),
                name="chk_password_reset_token_purpose",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="chk_password_reset_token_expires_gt_created",
            ),
        ]
        indexes = [
            models.Index(
                fields=["staff_user"],
                name="idx_password_reset_token_staff_user_id",
            ),
        ]

    def __str__(self) -> str:
        return f"PasswordResetToken(user={self.staff_user_id}, purpose={self.purpose})"


class TenantSetting(models.Model):
    """Doc 02 §5.12: Per-tenant key/value settings store (A-7)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=255)
    value = models.TextField()
    updated_by = models.ForeignKey(
        StaffUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tenant_settings",
        db_column="updated_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_setting"
        constraints = [
            models.UniqueConstraint(fields=["key"], name="uq_tenant_setting_key"),
        ]
        indexes = [
            models.Index(
                fields=["updated_by"], name="idx_tenant_setting_updated_by_id"
            ),
        ]

    def __str__(self) -> str:
        return f"TenantSetting(key={self.key})"


class AuditLog(models.Model):
    """Doc 02 §5.11 & §13: Append-only audit log of state changes.

    Inside the tenant schema. Zero updated_at, zero soft-delete, plain UUIDs
    for actor_id and entity_id.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=255)
    entity_id = models.UUIDField()
    before_jsonb = models.JSONField(null=True, blank=True)
    after_jsonb = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)  # noqa: DJ001
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(fields=["at"], name="idx_audit_log_at"),
            models.Index(
                fields=["entity_type", "entity_id"],
                name="idx_audit_log_entity_type_entity_id",
            ),
            models.Index(fields=["actor_id"], name="idx_audit_log_actor_id"),
        ]

    def __str__(self) -> str:
        return (
            f"AuditLog({self.action}, {self.entity_type}:{self.entity_id}, {self.at})"
        )
