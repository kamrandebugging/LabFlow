import uuid
from typing import TYPE_CHECKING, Any

from django.db import models

if TYPE_CHECKING:
    from apps.accounts.models import StaffBranch


class Branch(models.Model):
    """Doc 02 §5.1: A lab branch or collection centre inside the tenant schema."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=3)
    name = models.CharField(max_length=255)
    address = models.TextField(null=True, blank=True)  # noqa: DJ001
    phone = models.CharField(max_length=32, null=True, blank=True)  # noqa: DJ001
    is_collection_centre = models.BooleanField(default=False)
    result_entry_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "branch"
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uq_branch_code"),
        ]
        indexes = [
            models.Index(fields=["deleted_at"], name="idx_branch_deleted_at"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


def __getattr__(name: str) -> Any:
    if name == "StaffBranch":
        from apps.accounts.models import StaffBranch

        return StaffBranch
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["Branch", "StaffBranch"]
