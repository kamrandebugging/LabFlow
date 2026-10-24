# Re-export AuditLog for audit module access per Doc 01 §7 / Doc 02 §19
from apps.accounts.models import AuditLog

__all__ = ["AuditLog"]
