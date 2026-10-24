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
