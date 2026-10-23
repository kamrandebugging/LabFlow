"""Tenancy baseline model stubs for django-tenants configuration."""

from django_tenants.models import DomainMixin, TenantMixin


class Tenant(TenantMixin):
    """Tenant stub model satisfying django-tenants system checks prior to Subtask 2."""

    auto_create_schema = True

    class Meta:
        app_label = "core"


class Domain(DomainMixin):
    """Domain stub model satisfying django-tenants system checks prior to Subtask 2."""

    class Meta:
        app_label = "core"
