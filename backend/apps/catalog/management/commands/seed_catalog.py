"""Management command to seed standard 150 diagnostic tests catalog for tenants.

Usage:
    python manage.py seed_catalog [--tenant=<slug_or_schema>]
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from apps.catalog.models import Test
from apps.core.models import Tenant
from apps.platform.seeds import seed_tenant_p6_data


class Command(BaseCommand):
    help = "Seed standard 150 Pakistan diagnostic tests catalog for tenants."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--tenant",
            type=str,
            default=None,
            help="Tenant slug or schema name to seed. If omitted, seeds all tenants.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        tenant_ident = options.get("tenant")

        if tenant_ident:
            tenants = list(
                Tenant.objects.filter(schema_name=tenant_ident)
                | Tenant.objects.filter(slug=tenant_ident)
            )
            if not tenants:
                raise CommandError(f"Tenant not found for identifier: {tenant_ident!r}")
        else:
            tenants = list(Tenant.objects.exclude(schema_name="public").all())

        if not tenants:
            self.stdout.write(self.style.WARNING("No tenant schemas found to seed."))
            return

        for tenant in tenants:
            self.stdout.write(
                f"Seeding catalog for '{tenant.name}' ({tenant.schema_name})..."
            )
            with schema_context(tenant.schema_name):
                before_count = Test.objects.count()
                seed_tenant_p6_data(tenant)
                after_count = Test.objects.count()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Tenant '{tenant.slug}': {before_count} -> {after_count} tests."
                )
            )
