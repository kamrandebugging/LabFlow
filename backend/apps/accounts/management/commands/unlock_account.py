"""Owner unlock for a progressively locked account (LAB-49 Phase 5.6).

Usage: ``python manage.py unlock_account --tenant tenant_a --email a@b.com``

The lock is a Redis TTL value written after repeated throttled login windows;
this command clears it and the violation counter. The action is the operational
half of "Owner-unlockable, audited".
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.accounts.throttling import unlock_account


class Command(BaseCommand):
    help = "Clear a progressive login lockout for one staff account."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--tenant", required=True, help="Tenant schema name.")
        parser.add_argument("--email", required=True, help="Staff email address.")
        parser.add_argument(
            "--ip", default="", help="Client IP whose lock should be cleared."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.accounts.models import AuditLog, StaffUser

        tenant = str(options["tenant"])
        email = str(options["email"]).strip().lower()
        ip = str(options.get("ip") or "")
        with schema_context(tenant):
            unlock_account(tenant, email, ip)
            target = StaffUser.objects.filter(email=email).first()
            AuditLog.objects.create(
                actor_id=None,
                action="auth.account_unlocked",
                entity_type="staff_user",
                entity_id=target.id if target else uuid.uuid4(),
                before_jsonb=None,
                after_jsonb={"email": email, "by": "operator"},
                ip=None,
                user_agent="unlock_account command",
            )
        self.stdout.write(self.style.SUCCESS(f"Unlocked {email} on {tenant}."))
