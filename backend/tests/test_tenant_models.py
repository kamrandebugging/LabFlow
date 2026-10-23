"""Tests for core Tenant and Domain public models and factories."""

import pytest

from apps.core.models import Domain, Tenant
from tests.factories.core import DomainFactory, TenantFactory


@pytest.mark.django_db
def test_tenant_creation() -> None:
    """Verify Tenant model instantiation and string representation."""
    tenant = Tenant(
        slug="testlab",
        name="Test Laboratory",
        schema_name="tenant_testlab",
        status=Tenant.Status.ACTIVE,
    )
    assert str(tenant) == "Test Laboratory (testlab)"
    assert tenant.status == Tenant.Status.ACTIVE


@pytest.mark.django_db
def test_domain_creation() -> None:
    """Verify Domain model instantiation and string representation."""
    tenant = Tenant(
        slug="testlab2",
        name="Test Lab 2",
        schema_name="tenant_testlab2",
    )
    domain = Domain(
        domain="testlab2.localhost",
        tenant=tenant,
        is_primary=True,
    )
    assert str(domain) == "testlab2.localhost"
    assert domain.is_primary is True


@pytest.mark.django_db
def test_factories_build() -> None:
    """Verify TenantFactory and DomainFactory build instances."""
    tenant = TenantFactory.build()
    assert tenant.slug.startswith("lab")
    assert tenant.schema_name == f"tenant_{tenant.slug}"
    domain = DomainFactory.build(tenant=tenant)
    assert domain.tenant == tenant
    assert domain.is_primary is True
