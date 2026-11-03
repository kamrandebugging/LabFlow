"""
LAB-35 (KAN-160): Tests for tenant settings registry, accessor, and API.

Doc 04 §10 / Doc 02 §5.12: key-value store, accessor with fallback,
GET/PATCH /settings, 422 unknown_setting_key, per-key validation,
one audit row per key changed, new settings need no migration,
corrupted values degrade gracefully.
"""

from typing import Any

import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog, TenantSetting
from apps.platform.settings_accessor import (
    UnknownSettingKeyError,
    get_all_settings,
    get_setting,
    reset_setting,
    set_setting,
)
from apps.platform.settings_registry import (
    SETTING_REGISTRY,
    is_known_key,
    validate_setting,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_contains_six_doc10_keys() -> None:
    expected = {
        "billing_hold_enabled",
        "report_default_language",
        "report_link_validity_days",
        "transfer_late_after_hours",
        "brand_display_name",
        "brand_accent_colour",
    }
    assert set(SETTING_REGISTRY.keys()) == expected


def test_registry_new_key_needs_no_migration() -> None:
    """DoD: adding a key is registry-only — the DB table shape is unchanged."""
    field_names = {f.name for f in TenantSetting._meta.get_fields()}
    assert field_names >= {
        "id",
        "key",
        "value",
        "updated_by",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize(
    "key,raw,expected",
    [
        ("billing_hold_enabled", "true", True),
        ("billing_hold_enabled", "FALSE", False),
        ("report_default_language", "ur", "ur"),
        ("report_default_language", "EN", "en"),
        ("report_link_validity_days", "7", 7),
        ("report_link_validity_days", "30", 30),
        ("transfer_late_after_hours", "24", 24),
        ("brand_display_name", " City Lab ", "City Lab"),
        ("brand_accent_colour", "#0D9488", "#0d9488"),
    ],
)
def test_validate_setting_happy_paths(key: str, raw: str, expected: Any) -> None:
    assert validate_setting(key, raw) == expected


@pytest.mark.parametrize(
    "key,raw",
    [
        ("billing_hold_enabled", "yes"),
        ("billing_hold_enabled", "1"),
        ("report_default_language", "fr"),
        ("report_default_language", ""),
        ("report_link_validity_days", "0"),
        ("report_link_validity_days", "31"),
        ("report_link_validity_days", "abc"),
        ("transfer_late_after_hours", "0"),
        ("transfer_late_after_hours", "-5"),
        ("brand_display_name", "x" * 101),
        ("brand_accent_colour", "red"),
        ("brand_accent_colour", "#12345"),
        ("brand_accent_colour", "#gggggg"),
    ],
)
def test_validate_setting_rejects_invalid(key: str, raw: str) -> None:
    with pytest.raises(ValueError):
        validate_setting(key, raw)


def test_validate_setting_unknown_key_raises_key_error() -> None:
    with pytest.raises(KeyError):
        validate_setting("nope_not_a_key", "x")
    assert not is_known_key("nope_not_a_key")


# ---------------------------------------------------------------------------
# Accessor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_setting_falls_back_to_default_when_no_row(tenant_a: Any) -> None:
    with schema_context(tenant_a.schema_name):
        TenantSetting.objects.filter(key="billing_hold_enabled").delete()
        assert get_setting("billing_hold_enabled") is False
        assert get_setting("report_default_language") == "en"
        assert get_setting("report_link_validity_days") == 7


@pytest.mark.django_db
def test_get_setting_reads_stored_value(tenant_a: Any) -> None:
    with schema_context(tenant_a.schema_name):
        TenantSetting.objects.update_or_create(
            key="report_link_validity_days",
            defaults={"value": "14", "updated_by": None},
        )
        assert get_setting("report_link_validity_days") == 14


@pytest.mark.django_db
def test_get_setting_corrupt_value_degrades_to_default(tenant_a: Any) -> None:
    """DoD: corrupted value degrades gracefully — never crashes."""
    with schema_context(tenant_a.schema_name):
        TenantSetting.objects.update_or_create(
            key="report_link_validity_days",
            defaults={"value": "not-a-number", "updated_by": None},
        )
        # Must not raise; falls back to default 7.
        assert get_setting("report_link_validity_days") == 7

        TenantSetting.objects.update_or_create(
            key="billing_hold_enabled",
            defaults={"value": "maybe", "updated_by": None},
        )
        assert get_setting("billing_hold_enabled") is False


@pytest.mark.django_db
def test_get_setting_unknown_key_raises(tenant_a: Any) -> None:
    with schema_context(tenant_a.schema_name), pytest.raises(UnknownSettingKeyError):
        get_setting("does_not_exist")


@pytest.mark.django_db
def test_get_all_settings_returns_all_keys(tenant_a: Any) -> None:
    with schema_context(tenant_a.schema_name):
        all_settings = get_all_settings()
        assert set(all_settings.keys()) == set(SETTING_REGISTRY.keys())


@pytest.mark.django_db
def test_set_setting_persists_and_audits(tenant_a: Any, manager_user: Any) -> None:
    with schema_context(tenant_a.schema_name):
        parsed = set_setting(
            "report_link_validity_days", "14", manager_user.id, actor_ip="1.2.3.4"
        )
        assert parsed == 14
        assert get_setting("report_link_validity_days") == 14

        row = TenantSetting.objects.get(key="report_link_validity_days")
        assert row.updated_by_id == manager_user.id

        audit = AuditLog.objects.filter(
            action="tenant_setting.updated",
            entity_type="tenant_setting",
            entity_id=row.id,
        ).get()
        assert audit.actor_id == manager_user.id
        assert audit.after_jsonb == {"key": "report_link_validity_days", "value": "14"}
        assert audit.ip == "1.2.3.4"


@pytest.mark.django_db
def test_set_setting_unknown_key_raises_and_writes_no_audit(
    tenant_a: Any, manager_user: Any
) -> None:
    with schema_context(tenant_a.schema_name):
        before = AuditLog.objects.count()
        with pytest.raises(UnknownSettingKeyError):
            set_setting("bogus_key", "x", manager_user.id)
        assert AuditLog.objects.count() == before


@pytest.mark.django_db
def test_set_setting_invalid_value_raises_and_writes_no_audit(
    tenant_a: Any, manager_user: Any
) -> None:
    with schema_context(tenant_a.schema_name):
        before = AuditLog.objects.count()
        with pytest.raises(ValueError):
            set_setting("report_link_validity_days", "99", manager_user.id)
        assert AuditLog.objects.count() == before
        # Stored value unchanged (still default).
        assert get_setting("report_link_validity_days") == 7


@pytest.mark.django_db
def test_reset_setting_deletes_row_and_audits(tenant_a: Any, manager_user: Any) -> None:
    with schema_context(tenant_a.schema_name):
        set_setting("report_link_validity_days", "14", manager_user.id)
        assert get_setting("report_link_validity_days") == 14

        reset_setting("report_link_validity_days", manager_user.id)
        assert not TenantSetting.objects.filter(
            key="report_link_validity_days"
        ).exists()
        # Default applies again.
        assert get_setting("report_link_validity_days") == 7

        assert (
            AuditLog.objects.filter(
                action="tenant_setting.reset", entity_type="tenant_setting"
            ).count()
            == 1
        )


# ---------------------------------------------------------------------------
# API: GET /settings, PATCH /settings
# ---------------------------------------------------------------------------


@pytest.fixture
def manager_user(tenant_a: Any) -> Any:
    from django.contrib.auth.hashers import make_password
    from apps.accounts.models import Role, StaffUser

    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="manager@settingslab.com",
            password_hash=make_password("ManagerSecretPass123!"),
            role=Role.MANAGER,
            is_active=True,
        )


@pytest.fixture
def reception_user(tenant_a: Any) -> Any:
    from django.contrib.auth.hashers import make_password
    from apps.accounts.models import Role, StaffUser

    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="reception@settingslab.com",
            password_hash=make_password("ReceptionSecretPass123!"),
            role=Role.RECEPTION,
            is_active=True,
        )


def _make_token(user: Any, tenant_slug: str = "tenant_a") -> str:
    """Mint an access token directly, bypassing login (avoids rate limits)."""
    from apps.accounts.jwt_engine import mint_access_token

    token, _, _ = mint_access_token(
        staff_user_id=user.id,
        tenant_slug=tenant_slug,
        role=user.role,
    )
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
def test_api_get_settings_returns_all(tenant_a: Any, manager_user: Any) -> None:
    from django.test import Client

    client = Client(HTTP_HOST="tenant-a.localhost")
    token = _make_token(manager_user)

    resp = client.get("/api/v1/settings", **_auth_headers(token))  # type: ignore[arg-type]
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["settings"].keys()) == set(SETTING_REGISTRY.keys())
    assert data["settings"]["report_default_language"]["value"] == "en"
    assert data["settings"]["report_default_language"]["default"] == "en"


@pytest.mark.django_db
def test_api_patch_settings_updates_and_audits(
    tenant_a: Any, manager_user: Any
) -> None:
    from django.test import Client

    client = Client(HTTP_HOST="tenant-a.localhost")
    token = _make_token(manager_user)

    resp = client.patch(
        "/api/v1/settings",
        {"settings": {"report_link_validity_days": "14"}},
        content_type="application/json",
        **_auth_headers(token),  # type: ignore[arg-type]
    )
    assert resp.status_code == 200
    assert resp.json()["settings"]["report_link_validity_days"]["value"] == 14

    with schema_context(tenant_a.schema_name):
        assert get_setting("report_link_validity_days") == 14
        assert (
            AuditLog.objects.filter(
                action="tenant_setting.updated", entity_type="tenant_setting"
            ).count()
            == 1
        )


@pytest.mark.django_db
def test_api_patch_unknown_key_returns_422(tenant_a: Any, manager_user: Any) -> None:
    from django.test import Client

    client = Client(HTTP_HOST="tenant-a.localhost")
    token = _make_token(manager_user)

    resp = client.patch(
        "/api/v1/settings",
        {"settings": {"nope_not_a_key": "x"}},
        content_type="application/json",
        **_auth_headers(token),  # type: ignore[arg-type]
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "unknown_setting_key"


@pytest.mark.django_db
def test_api_patch_invalid_value_returns_422(tenant_a: Any, manager_user: Any) -> None:
    from django.test import Client

    client = Client(HTTP_HOST="tenant-a.localhost")
    token = _make_token(manager_user)

    resp = client.patch(
        "/api/v1/settings",
        {"settings": {"report_link_validity_days": "99"}},
        content_type="application/json",
        **_auth_headers(token),  # type: ignore[arg-type]
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_setting_value"


@pytest.mark.django_db
def test_api_patch_requires_manager_role(tenant_a: Any, reception_user: Any) -> None:
    from django.test import Client

    client = Client(HTTP_HOST="tenant-a.localhost")
    token = _make_token(reception_user)

    resp = client.patch(
        "/api/v1/settings",
        {"settings": {"report_link_validity_days": "14"}},
        content_type="application/json",
        **_auth_headers(token),  # type: ignore[arg-type]
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_api_get_settings_unauthenticated_returns_401(tenant_a: Any) -> None:
    from django.test import Client

    client = Client(HTTP_HOST="tenant-a.localhost")
    resp = client.get("/api/v1/settings")
    assert resp.status_code == 401
