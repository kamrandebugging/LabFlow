"""Per-tenant role enablement (D1, FR-1, S1).

The Platform decides which of the four creatable roles a lab may use. The
tenant server is the only source of truth: every staff create/edit re-checks
the enablement list stored on the public ``Tenant`` row (``enabled_roles``).
A role list sent by a client is never trusted.

The Owner role is always enabled and is never stored as disabled. Legacy
platform writes used the label ``receptionist``; that alias is normalised to
the canonical ``reception`` value used by ``Role``.
"""

from __future__ import annotations

from django.db import connection

from apps.accounts.models import Role
from apps.core.models import Tenant

# The four roles the Platform may enable/disable per lab.
CREATABLE_ROLES: tuple[str, ...] = (
    Role.MANAGER,
    Role.RECEPTION,
    Role.TECHNICIAN,
    Role.PATHOLOGIST,
)

# D-G: Owner + Reception + Technician on for a newly provisioned lab.
DEFAULT_ENABLED_ROLES: tuple[str, ...] = (
    Role.OWNER,
    Role.RECEPTION,
    Role.TECHNICIAN,
)

ROLE_LABELS: dict[str, str] = {
    Role.OWNER: "Lab Owner",
    Role.MANAGER: "Branch Manager",
    Role.RECEPTION: "Receptionist / Collection Staff",
    Role.TECHNICIAN: "Lab Technician",
    Role.PATHOLOGIST: "Pathologist",
}

ROLE_ALIASES: dict[str, str] = {
    "receptionist": Role.RECEPTION,
    "reception": Role.RECEPTION,
    "owner": Role.OWNER,
    "manager": Role.MANAGER,
    "technician": Role.TECHNICIAN,
    "pathologist": Role.PATHOLOGIST,
}


def normalize_role(value: object) -> str | None:
    """Return the canonical role key for ``value``, or None when unknown."""
    if value is None:
        return None
    return ROLE_ALIASES.get(str(value).strip().lower())


def normalize_role_list(values: object) -> list[str]:
    """Normalise a role list, dropping unknown/duplicate entries.

    ``owner`` is always present in the returned list and is placed first.
    """
    if not isinstance(values, (list, tuple, set)):
        values = []
    result: list[str] = []
    for value in values:
        role = normalize_role(value)
        if role and role not in result:
            result.append(role)
    if Role.OWNER not in result:
        result.insert(0, Role.OWNER)
    return result


def get_current_tenant() -> Tenant | None:
    """Resolve the public Tenant row for the active schema (None in tests)."""
    schema_name = getattr(connection, "schema_name", None)
    if not schema_name or schema_name == "public":
        return None
    return Tenant.objects.filter(schema_name=schema_name).first()


def effective_enabled_roles(tenant: Tenant | None) -> list[str]:
    """Enabled roles for a tenant, always including Owner.

    Fail closed: an unknown schema, or a legacy row with an empty list, gets
    Owner only. The D-G defaults are written explicitly at provisioning time,
    never inferred from an empty array (D1: no API call may create a role the
    Platform never enabled).
    """
    if tenant is None:
        return [Role.OWNER]
    if not tenant.enabled_roles:
        return [Role.OWNER]
    return normalize_role_list(list(tenant.enabled_roles))


def enabled_roles_for_current_tenant() -> list[str]:
    return effective_enabled_roles(get_current_tenant())


def session_enabled_roles() -> list[str] | None:
    """Enabled roles for the auth payload, or None for legacy rows.

    ``Tenant.enabled_roles`` was added with an empty-list default and no
    backfill. Returning an empty list as "Owner only" would lock every
    pre-existing non-Owner staff account out of the SPA. A tenant with no
    explicit list therefore keeps the pre-feature behaviour; only an explicit
    Platform choice is enforced as a session gate.
    """
    tenant = get_current_tenant()
    if tenant is None or not tenant.enabled_roles:
        return None
    return effective_enabled_roles(tenant)


def is_role_enabled_for_current_tenant(role: str) -> bool:
    normalized = normalize_role(role)
    return bool(normalized and normalized in enabled_roles_for_current_tenant())


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, str(role).replace("_", " ").title())
