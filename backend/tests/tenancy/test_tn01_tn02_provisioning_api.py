import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from django.conf import settings
from django.db import IntegrityError
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.core.models import (
    Domain,
    PlatformAudit,
    Subscription,
    Tenant,
)
from apps.platform.provisioning import RESERVED_SLUGS, validate_slug
from tests.factories import PlanFactory, PlatformUserFactory, StaffUserFactory

EXPECTED_RESERVED_SLUGS = {
    "www",
    "api",
    "admin",
    "app",
    "platform",
    "internal",
    "static",
    "media",
    "assets",
    "cdn",
    "n8n",
    "sentry",
    "minio",
    "staging",
    "health",
    "metrics",
    "login",
    "signup",
    "register",
    "account",
    "billing",
    "support",
    "help",
    "mail",
    "smtp",
    "imap",
    "ftp",
    "public",
    "tenant",
    "tenants",
    "system",
    "root",
    "labflow",
    "test",
    "demo",
    "example",
    "null",
}


def _platform_jwt(user: Any) -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    return str(
        jwt.encode(
            {
                "sub": str(user.id),
                "role": "super_admin",
                "typ": "access",
            },
            str(signing_key),
            algorithm="HS256",
        )
    )


def _tenant_staff_jwt(staff_id: uuid.UUID | Any, tenant_slug: str = "tenant_a") -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    return str(
        jwt.encode(
            {
                "sub": str(staff_id),
                "tenant": tenant_slug,
                "role": "owner",
                "typ": "access",
            },
            str(signing_key),
            algorithm="HS256",
        )
    )


@pytest.mark.django_db
class TestSlugValidationRules:
    """TN-01 & TN-02: Slug format and reserved list validation (Doc 04 §5.1)."""

    @pytest.mark.parametrize(
        "invalid_slug",
        [
            "CityLab",  # uppercase
            "city-lab",  # hyphen
            "1citylab",  # leading digit
            "ab",  # 2 chars (< 3)
            "a" * 31,  # 31 chars (> 30)
            "city_lab",  # underscore
            "",  # empty
        ],
    )
    def test_tn01_invalid_slugs_refused(self, invalid_slug: str) -> None:
        from apps.platform.provisioning import ProvisioningError

        with pytest.raises(ProvisioningError) as exc_info:
            validate_slug(invalid_slug)
        assert exc_info.value.code == "slug_invalid"
        assert exc_info.value.status_code == 422

    @pytest.mark.parametrize("valid_slug", ["citylab", "lab2", "abc", "a" + "0" * 29])
    def test_tn01_valid_slugs_accepted(self, valid_slug: str) -> None:
        assert validate_slug(valid_slug) == valid_slug

    def test_tn02_reserved_slugs_constant_pinned_and_refused(self) -> None:
        from apps.platform.provisioning import ProvisioningError

        assert EXPECTED_RESERVED_SLUGS.issubset(RESERVED_SLUGS)
        assert len(RESERVED_SLUGS) == len(EXPECTED_RESERVED_SLUGS)
        for reserved in EXPECTED_RESERVED_SLUGS:
            with pytest.raises(ProvisioningError) as exc_info:
                validate_slug(reserved)
            assert exc_info.value.code == "slug_reserved"
            assert exc_info.value.status_code == 422


@pytest.mark.django_db(transaction=True)
class TestPlatformTenantProvisioningAPI:
    """Subtask 1 (KAN-72): P-1 validate, P-2 atomic insert, enqueue on commit."""

    def test_auth_boundary_rejects_unauthenticated_and_tenant_staff(
        self, tenant_a: Tenant
    ) -> None:
        client = APIClient()
        plan = PlanFactory(is_active=True)
        payload = {
            "name": "Chughtai Lab",
            "slug": "chughtailab",
            "plan_id": str(plan.id),
            "owner_email": "owner@chughtai.pk",
            "owner_name": "Dr. Omar Chughtai",
        }

        # 1. Unauthenticated -> 401
        res_unauth = client.post(
            "/api/v1/platform/tenants",
            payload,
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_unauth.status_code == 401

        # 2. Tenant StaffUser credentials -> 401 (never allowed on platform surface)
        with schema_context(tenant_a.schema_name):
            staff = StaffUserFactory(role="owner")
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_tenant_staff_jwt(staff.id, tenant_a.slug)}"
        )
        res_staff = client.post(
            "/api/v1/platform/tenants",
            payload,
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_staff.status_code == 401

        # 3. PlatformUser without TOTP enabled -> 403 totp_required (Doc 04 §12.1)
        sa_no_totp = PlatformUserFactory(totp_enabled=False, is_active=True)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(sa_no_totp)}")
        res_no_totp = client.post(
            "/api/v1/platform/tenants",
            payload,
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_no_totp.status_code == 403
        assert res_no_totp.json()["code"] == "totp_required"

    def test_p1_validation_errors(self) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        inactive_plan = PlanFactory(is_active=False)
        active_plan = PlanFactory(is_active=True)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(sa)}")

        # Invalid slug
        res_slug = client.post(
            "/api/v1/platform/tenants",
            {
                "name": "City Lab",
                "slug": "bad-slug",
                "plan_id": str(active_plan.id),
                "owner_email": "owner@citylab.pk",
                "owner_name": "Dr. Khan",
            },
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_slug.status_code == 422
        assert res_slug.json()["code"] == "slug_invalid"

        # Reserved slug
        res_reserved = client.post(
            "/api/v1/platform/tenants",
            {
                "name": "Admin Lab",
                "slug": "admin",
                "plan_id": str(active_plan.id),
                "owner_email": "owner@citylab.pk",
                "owner_name": "Dr. Khan",
            },
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_reserved.status_code == 422
        assert res_reserved.json()["code"] == "slug_reserved"

        # Inactive plan
        res_plan = client.post(
            "/api/v1/platform/tenants",
            {
                "name": "City Lab",
                "slug": "citylab",
                "plan_id": str(inactive_plan.id),
                "owner_email": "owner@citylab.pk",
                "owner_name": "Dr. Khan",
            },
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_plan.status_code == 422
        assert res_plan.json()["code"] == "plan_inactive"

        # Invalid owner email
        res_email = client.post(
            "/api/v1/platform/tenants",
            {
                "name": "City Lab",
                "slug": "citylab",
                "plan_id": str(active_plan.id),
                "owner_email": "not-an-email",
                "owner_name": "Dr. Khan",
            },
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_email.status_code == 422
        assert res_email.json()["code"] == "validation_error"

    def test_p2_creates_tenant_domain_subscription_audit_and_enqueues_on_commit(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True, price=Decimal("15000.00"))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(sa)}")

        with patch(
            "apps.platform.provisioning.provision_tenant_task.delay"
        ) as mock_delay:
            response = client.post(
                "/platform/tenants",
                {
                    "name": "Excel Labs",
                    "slug": "excellabs",
                    "plan_id": str(plan.id),
                    "owner": {
                        "email": "owner@excellabs.pk",
                        "name": "Dr. Ayesha",
                    },
                },
                format="json",
                HTTP_HOST="localhost",
                HTTP_IDEMPOTENCY_KEY="idem-excel-001",
            )

        assert response.status_code == 202
        body: dict[str, Any] = response.json()
        assert body["slug"] == "excellabs"
        assert body["status"] == "provisioning"
        assert body["schema_name"] == "tenant_excellabs"

        tenant = Tenant.objects.get(slug="excellabs")
        assert tenant.status == "provisioning"
        assert tenant.schema_name == "tenant_excellabs"

        domain = Domain.objects.get(tenant=tenant)
        assert domain.is_primary is True
        assert domain.domain.startswith("excellabs.")

        sub = Subscription.objects.get(tenant=tenant)
        assert sub.plan_id == plan.id
        assert sub.status == "active"

        audit = PlatformAudit.objects.get(action="tenant.created", entity_id=tenant.id)
        assert audit.actor_id == sa.id

        # Task enqueued with tenant_slug as sole argument
        mock_delay.assert_called_once_with("excellabs")

        # Duplicate slug without matching idempotency key -> 409 slug_taken
        res_dup = client.post(
            "/api/v1/platform/tenants",
            {
                "name": "Excel Labs Duplicate",
                "slug": "excellabs",
                "plan_id": str(plan.id),
                "owner_email": "other@excellabs.pk",
                "owner_name": "Dr. Other",
            },
            format="json",
            HTTP_HOST="localhost",
        )
        assert res_dup.status_code == 409
        assert res_dup.json()["code"] == "slug_taken"
        assert Tenant.objects.filter(slug="excellabs").count() == 1

    def test_p2_atomicity_rolls_back_all_rows_and_never_enqueues_on_midway_failure(
        self,
    ) -> None:
        sa = PlatformUserFactory(totp_enabled=True, is_active=True)
        plan = PlanFactory(is_active=True)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_platform_jwt(sa)}")

        with (
            patch(
                "apps.platform.provisioning.Subscription.objects.create",
                side_effect=IntegrityError("Simulated subscription failure"),
            ),
            patch(
                "apps.platform.provisioning.provision_tenant_task.delay"
            ) as mock_delay,
        ):
            response = client.post(
                "/api/v1/platform/tenants",
                {
                    "name": "Atomic Rollback Lab",
                    "slug": "atomiclab",
                    "plan_id": str(plan.id),
                    "owner_email": "owner@atomic.pk",
                    "owner_name": "Dr. Atomic",
                },
                format="json",
                HTTP_HOST="localhost",
            )

        assert response.status_code == 409
        assert Tenant.objects.filter(slug="atomiclab").exists() is False
        assert Domain.objects.filter(domain__startswith="atomiclab.").exists() is False
        assert Subscription.objects.filter(tenant__slug="atomiclab").exists() is False
        mock_delay.assert_not_called()
