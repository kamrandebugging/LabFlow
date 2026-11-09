"""
LAB-35 (KAN-160): Tenant settings accessor.

`get_setting(key)` returns the parsed value for a tenant setting:
- Reads the tenant's `tenant_setting` row for the key.
- Falls back to the registry default if no row exists.
- Logs an error and falls back to default if the stored value is corrupt.
- NEVER crashes — always returns a valid parsed value for known keys.

`set_setting(key, raw_value, updated_by)` validates and persists a new value,
writing one audit row per key changed.
"""

import logging
from typing import Any
from uuid import UUID

from django.db import connection, transaction

from apps.accounts.models import AuditLog, TenantSetting
from apps.platform.settings_registry import (
    SETTING_REGISTRY,
    get_default,
    is_known_key,
    validate_setting,
)

logger = logging.getLogger(__name__)


class UnknownSettingKeyError(KeyError):
    """Raised when a setting key is not in the registry."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Unknown setting key: {key!r}")
        self.key = key


def get_setting(key: str) -> Any:
    """Return the parsed value for a tenant setting key.

    Contract (Doc 04 §10):
    - Unknown key → raises UnknownSettingKeyError.
    - No row → returns parsed default.
    - Corrupt value → logs error, returns parsed default.
    - Never raises for a known key with any stored value.

    Must be called inside the tenant schema context.
    """
    if not is_known_key(key):
        raise UnknownSettingKeyError(key)

    spec = SETTING_REGISTRY[key]
    try:
        row = TenantSetting.objects.filter(key=key).first()
    except Exception:
        # DB unreachable or schema issue — degrade to default, never crash.
        logger.exception("get_setting(%r): database read failed, using default", key)
        return spec.validator(get_default(key))

    if row is None:
        if key == "brand_display_name":
            tenant = getattr(connection, "tenant", None)
            if tenant and getattr(tenant, "name", None):
                return tenant.name
            schema_name = getattr(connection, "schema_name", None)
            if schema_name and schema_name != "public":
                from apps.core.models import Tenant

                t = Tenant.objects.filter(schema_name=schema_name).first()
                if t and t.name:
                    return t.name
        return spec.validator(get_default(key))

    if key == "brand_display_name" and (not row.value or not row.value.strip()):
        tenant = getattr(connection, "tenant", None)
        if tenant and getattr(tenant, "name", None):
            return tenant.name
        schema_name = getattr(connection, "schema_name", None)
        if schema_name and schema_name != "public":
            from apps.core.models import Tenant

            t = Tenant.objects.filter(schema_name=schema_name).first()
            if t and t.name:
                return t.name

    try:
        return spec.validator(row.value)
    except (ValueError, AttributeError, TypeError) as exc:
        # Corrupted value degrades gracefully (DoD).
        logger.error(
            "get_setting(%r): corrupt stored value %r (%s); using default %r",
            key,
            row.value,
            exc,
            get_default(key),
        )
        return spec.validator(get_default(key))


def get_all_settings() -> dict[str, Any]:
    """Return parsed values for all registered settings.

    Never crashes; corrupt values fall back to defaults per key.
    """
    return {key: get_setting(key) for key in SETTING_REGISTRY}


def set_setting(
    key: str,
    raw_value: str,
    updated_by: UUID | None,
    *,
    actor_ip: str | None = None,
    user_agent: str | None = None,
) -> Any:
    """Validate and persist a tenant setting value.

    - Unknown key → raises UnknownSettingKeyError (API maps to 422).
    - Invalid value → raises ValueError (API maps to 422).
    - Writes one audit_log row per key changed, in the same transaction.

    Returns the parsed value. Must be called inside the tenant schema context.
    """
    if not is_known_key(key):
        raise UnknownSettingKeyError(key)

    # Validate BEFORE touching the DB — ValueError propagates to the caller.
    parsed = validate_setting(key, raw_value)

    with transaction.atomic():
        row, created = TenantSetting.objects.get_or_create(
            key=key,
            defaults={"value": raw_value.strip(), "updated_by_id": updated_by},
        )
        before_value: str | None = None
        if not created:
            before_value = row.value
            row.value = raw_value.strip()
            row.updated_by_id = updated_by
            row.save(update_fields=["value", "updated_by", "updated_at"])

        # One audit row per key changed (Doc 02 §5.12, ticket §3).
        AuditLog.objects.create(
            actor_id=updated_by,
            action="tenant_setting.updated",
            entity_type="tenant_setting",
            entity_id=row.id,
            before_jsonb={"key": key, "value": before_value},
            after_jsonb={"key": key, "value": row.value},
            ip=actor_ip,
            user_agent=user_agent,
        )

    return parsed


def reset_setting(
    key: str,
    updated_by: UUID | None,
    *,
    actor_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Delete a tenant setting row so the platform default applies again.

    Doc 02 §5.12: resetting deletes the row. One audit row is written.
    Unknown key → raises UnknownSettingKeyError.
    """
    if not is_known_key(key):
        raise UnknownSettingKeyError(key)

    with transaction.atomic():
        row = TenantSetting.objects.filter(key=key).first()
        if row is None:
            return
        before_value = row.value
        entity_id = row.id
        row.delete()

        AuditLog.objects.create(
            actor_id=updated_by,
            action="tenant_setting.reset",
            entity_type="tenant_setting",
            entity_id=entity_id,
            before_jsonb={"key": key, "value": before_value},
            after_jsonb={"key": key, "value": None},
            ip=actor_ip,
            user_agent=user_agent,
        )
