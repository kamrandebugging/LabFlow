"""
LAB-35 (KAN-160): Tenant settings registry.

Doc 04 §10: Per-tenant key/value settings. Each key has a type, default,
validator, and description. New settings are added to the registry — never
requiring a migration (Doc 02 §5.12).

The six keys from Doc 04 §10.2 / seeds P-7:
- billing_hold_enabled: bool — block new invoices when True
- report_default_language: "en" | "ur" — patient-facing messages (A-16)
- report_link_validity_days: int 1-30 — signed report link TTL
- transfer_late_after_hours: int >= 1 — transfer exception threshold
- brand_display_name: str — tenant display name on reports
- brand_accent_colour: hex colour — brand accent on reports
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_HEX_COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_bool(value: str) -> bool:
    """Parse 'true'/'false' (case-insensitive). Raises ValueError if invalid."""
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Invalid boolean value: {value!r} (expected 'true' or 'false')")


def _validate_language(value: str) -> str:
    """Validate report language code. Raises ValueError if invalid."""
    normalized = value.strip().lower()
    if normalized in ("en", "ur"):
        return normalized
    raise ValueError(f"Invalid language: {value!r} (expected 'en' or 'ur')")


def _validate_link_validity_days(value: str) -> int:
    """Validate report link validity days (1-30). Raises ValueError if invalid."""
    try:
        days = int(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid integer: {value!r}") from exc
    if not 1 <= days <= 30:
        raise ValueError(f"Out of range: {days} (expected 1-30 days)")
    return days


def _validate_transfer_late_hours(value: str) -> int:
    """Validate transfer late threshold hours (>= 1). Raises ValueError if invalid."""
    try:
        hours = int(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid integer: {value!r}") from exc
    if hours < 1:
        raise ValueError(f"Out of range: {hours} (expected >= 1 hour)")
    return hours


def _validate_display_name(value: str) -> str:
    """Validate brand display name (max 100 chars; empty means 'use tenant name')."""
    stripped = value.strip()
    if len(stripped) > 100:
        raise ValueError("Display name must not exceed 100 characters")
    return stripped


def _validate_accent_colour(value: str) -> str:
    """Validate hex colour (#rrggbb). Raises ValueError if invalid."""
    stripped = value.strip()
    if not _HEX_COLOUR_RE.match(stripped):
        raise ValueError(f"Invalid hex colour: {value!r} (expected #rrggbb)")
    return stripped.lower()


@dataclass(frozen=True)
class SettingSpec:
    """Specification for a single tenant setting key."""

    key: str
    type_name: str
    default: str
    validator: Callable[[str], Any]
    description: str


# Registry of all known tenant setting keys (Doc 04 §10.2).
# New settings are added HERE — no migration needed (Doc 02 §5.12 DoD).
SETTING_REGISTRY: dict[str, SettingSpec] = {
    "billing_hold_enabled": SettingSpec(
        key="billing_hold_enabled",
        type_name="bool",
        default="false",
        validator=_validate_bool,
        description="Block new invoice creation when true (Doc 03 OQ-33).",
    ),
    "report_default_language": SettingSpec(
        key="report_default_language",
        type_name="language",
        default="en",
        validator=_validate_language,
        description="Default language for patient-facing messages (A-16).",
    ),
    "report_link_validity_days": SettingSpec(
        key="report_link_validity_days",
        type_name="int",
        default="7",
        validator=_validate_link_validity_days,
        description="Signed report link validity in days (1-30).",
    ),
    "transfer_late_after_hours": SettingSpec(
        key="transfer_late_after_hours",
        type_name="int",
        default="24",
        validator=_validate_transfer_late_hours,
        description="Hours after which a transfer is flagged late.",
    ),
    "brand_display_name": SettingSpec(
        key="brand_display_name",
        type_name="string",
        default="",
        validator=_validate_display_name,
        description="Tenant display name shown on reports.",
    ),
    "brand_accent_colour": SettingSpec(
        key="brand_accent_colour",
        type_name="colour",
        default="#0d9488",
        validator=_validate_accent_colour,
        description="Brand accent colour as #rrggbb hex.",
    ),
}


def is_known_key(key: str) -> bool:
    """Return True if the key is in the registry."""
    return key in SETTING_REGISTRY


def get_default(key: str) -> str:
    """Return the default raw string value for a known key.

    Raises KeyError for unknown keys.
    """
    return SETTING_REGISTRY[key].default


def validate_setting(key: str, raw_value: str) -> Any:
    """Validate a raw string value for a known key, returning the parsed value.

    Raises:
        KeyError: if the key is not in the registry (unknown_setting_key).
        ValueError: if the value fails per-key validation.
    """
    spec = SETTING_REGISTRY[key]  # KeyError for unknown keys
    return spec.validator(raw_value)
