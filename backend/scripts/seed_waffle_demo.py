"""Seed demo samples for the waffle on a tenant, through the ORM.

Run inside the backend container:
    python manage.py shell -c "exec(open('/app/scripts/seed_waffle_demo.py').read())"

Creates 250 Sample rows spread across the last 14 days with a realistic status
mix so the "Checks per day" waffle shows real, non-empty data. Nothing is
fabricated in the frontend: these are real rows in the tenant schema.
"""

import random
from datetime import timedelta

from django.utils import timezone
from django_tenants.utils import schema_context

from apps.billing.models import Invoice
from apps.branches.models import Branch
from apps.core.models import Tenant
from apps.samples.models import Sample

TENANT_SLUG = "muse"
COUNT = 250
SPREAD_DAYS = 14
PREFIX = "SEED-"

# Weighted mix: mostly ready/collected, some in-process, a few rejected.
STATUS_WEIGHTS = [
    ("ready", 45),
    ("collected", 25),
    ("in_process", 12),
    ("received", 8),
    ("rejected", 6),
    ("cancelled", 4),
]


def pick_status() -> str:
    bag = []
    for status, weight in STATUS_WEIGHTS:
        bag.extend([status] * weight)
    return random.choice(bag)


tenant = Tenant.objects.get(slug=TENANT_SLUG)
print("tenant:", tenant.name, tenant.schema_name)

with schema_context(tenant.schema_name):
    invoice = Invoice.objects.order_by("created_at").first()
    branch = Branch.objects.order_by("created_at").first()
    if invoice is None or branch is None:
        raise SystemExit("No invoice/branch in this tenant; cannot seed samples.")

    existing = set(
        Sample.objects.filter(accession_id__startswith=PREFIX).values_list(
            "accession_id", flat=True
        )
    )

    now = timezone.now()
    created = 0
    for i in range(COUNT):
        accession = f"{PREFIX}{i:04d}"
        if accession in existing:
            continue
        day_offset = i % SPREAD_DAYS
        collected = now - timedelta(
            days=day_offset,
            hours=random.randint(0, 9),
            minutes=random.randint(0, 59),
        )
        Sample.objects.create(
            invoice=invoice,
            branch=branch,
            accession_id=accession,
            status=pick_status(),
            collected_at=collected,
        )
        created += 1

    print("samples created:", created)
    print("samples total:", Sample.objects.count())
