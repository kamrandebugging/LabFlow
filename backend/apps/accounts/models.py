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
