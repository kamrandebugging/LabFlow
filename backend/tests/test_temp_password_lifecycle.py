"""Owner-ordered temp-password lifecycle tests.

A provisioning credential is shown once at creation. The registry stores only
its Argon2 hash (never plaintext), the tenant detail API never returns it, and
first login / password change removes the hash.
"""

from __future__ import annotations

import importlib
import uuid
from decimal import Decimal
from typing import cast

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from django_tenants.utils import schema_context, tenant_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, StaffUser
from apps.core.models import Plan, Tenant
from apps.platform.platform_jwt import platform_mint_access_token
from tests.factories.accounts import StaffUserFactory
from tests.factories.core import PlatformUserFactory, TenantFactory

_scrub_rows = importlib.import_module(
    "apps.core.migrations.0009_tenant_temp_password_hash"
)._scrub_rows


def _platform_client() -> APIClient:
    cache.clear()
    user = PlatformUserFactory(totp_enabled=True)
    token, _jti, _exp = platform_mint_access_token(user.id, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_tenant_detail_never_returns_temp_password() -> None:
    tenant = TenantFactory(
        slug=f"detail{uuid.uuid4().hex[:6]}",
        name="Detail Lab",
        temp_password="LBF-SENTINEL-9#",
        temp_password_hash=make_password("LBF-SENTINEL-9#"),
    )
    resp = _platform_client().get(
        f"/api/v1/platform/tenants/{tenant.id}", HTTP_HOST="localhost"
    )
    assert resp.status_code == 200, resp.content[:300]
    body = resp.json()
    assert "temp_password" not in body
    assert "temp_password_expires_at" not in body
    assert "LBF-SENTINEL-9#" not in resp.content.decode()


@pytest.mark.django_db
def test_provisioning_shows_credential_once_and_stores_only_hash() -> None:
    cache.clear()
    plan = Plan.objects.create(
        name="Temp Lifecycle Plan",
        price=Decimal("2999.00"),
        max_branches=1,
        max_staff=5,
        is_active=True,
    )
    slug = f"once{uuid.uuid4().hex[:6]}"
    resp = _platform_client().post(
        "/api/v1/platform/tenants",
        data={
            "name": "One Time Lab",
            "slug": slug,
            "plan_id": str(plan.id),
            "owner_name": "Dr. One Time",
            "owner_email": "once@example.com",
            "city": "Lahore",
            "province": "Punjab",
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert resp.status_code == 202, resp.content[:300]
    one_time = resp.json()["temp_password"]
    assert one_time.startswith("LBF-")
    assert one_time.endswith("#")

    tenant = Tenant.objects.get(slug=slug)
    assert tenant.temp_password == ""
    assert tenant.temp_password_hash
    assert tenant.temp_password_hash != one_time
    assert check_password(one_time, tenant.temp_password_hash)


@pytest.mark.django_db
def test_first_login_clears_stored_temp_credential(tenant_a: Tenant) -> None:
    cache.clear()
    temp_password = "LBF-FIRST-1#"
    email = "firstlogin@example.pk"
    with schema_context("public"):
        Tenant.objects.filter(pk=tenant_a.pk).update(
            temp_password=temp_password,
            temp_password_hash=make_password(temp_password),
            temp_password_expires_at=timezone.now(),
        )
    with tenant_context(tenant_a):
        owner = cast(
            StaffUser,
            StaffUserFactory(
                role=Role.OWNER,
                branch=None,
                email=email,
                password_hash=make_password(temp_password),
                password_is_temporary=True,
                is_active=True,
            ),
        )
        owner_id = owner.id

    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login",
        data={"email": email, "password": temp_password},
        format="json",
        HTTP_HOST="tenant-a.localhost",
    )
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json()["user"]["must_change_password"] is True

    tenant = Tenant.objects.get(pk=tenant_a.pk)
    assert tenant.temp_password == ""
    assert tenant.temp_password_hash == ""
    assert tenant.temp_password_expires_at is None

    with tenant_context(tenant_a):
        persisted = StaffUser.objects.get(pk=owner_id)
        # Login is unaffected: the hashed staff password remains the source.
        assert check_password(temp_password, persisted.password_hash)


@pytest.mark.django_db
def test_migration_scrubs_plaintext_when_owner_changed_password(
    tenant_a: Tenant,
) -> None:
    with schema_context("public"):
        Tenant.objects.filter(pk=tenant_a.pk).update(
            temp_password="LBF-LEGACY-7#",
            temp_password_hash="",
            temp_password_expires_at=timezone.now(),
        )
    with tenant_context(tenant_a):
        StaffUserFactory(
            role=Role.OWNER,
            branch=None,
            password_hash=make_password("ChangedPass123!"),
            password_is_temporary=False,
            is_active=True,
        )

    with connection.schema_editor() as editor:
        scrubbed = _scrub_rows(django_apps, editor)

    assert scrubbed >= 1
    tenant = Tenant.objects.get(pk=tenant_a.pk)
    assert tenant.temp_password == ""
    assert tenant.temp_password_hash == ""
    assert tenant.temp_password_expires_at is None
