"""Tests for PlatformUser and PlatformAudit public models per Doc 02 §4.1."""

import uuid

import pytest
from django.db import IntegrityError

from apps.core.models import PlatformAudit, PlatformUser
from tests.factories.core import PlatformAuditFactory, PlatformUserFactory


@pytest.mark.django_db
def test_platform_user_creation_and_password_hashing() -> None:
    """PlatformUser creates cleanly and password hashing operates per Argon2."""
    user = PlatformUser(
        email="operator@labflow.app",
        totp_enabled=True,
        totp_secret_encrypted="test-encrypted-secret",
        totp_backup_codes_hash=["hash1", "hash2"],
    )
    user.set_password("AdminSecurePassword123!")
    user.save()

    assert user.id is not None
    assert user.email == "operator@labflow.app"
    assert user.check_password("AdminSecurePassword123!") is True
    assert user.check_password("WrongPassword") is False
    assert user.totp_backup_codes_hash == ["hash1", "hash2"]
    assert str(user) == "operator@labflow.app"


@pytest.mark.django_db
def test_platform_user_email_uniqueness_enforced() -> None:
    """PostgreSQL rejects duplicate email for PlatformUser."""
    PlatformUser.objects.create(
        email="duplicate@labflow.app",
        password_hash="argon2$fakehash",
    )
    with pytest.raises(IntegrityError):
        PlatformUser.objects.create(
            email="duplicate@labflow.app",
            password_hash="argon2$fakehash2",
        )


@pytest.mark.django_db
def test_platform_audit_append_only_shape() -> None:
    """PlatformAudit model has creation timestamp only —
    zero updated_at or soft-delete columns.
    """
    actor_uuid = uuid.uuid4()
    target_uuid = uuid.uuid4()

    audit = PlatformAudit.objects.create(
        actor_id=actor_uuid,
        action="tenant.suspended",
        entity_type="tenant",
        entity_id=target_uuid,
        before_jsonb={"status": "active"},
        after_jsonb={"status": "suspended"},
        ip="192.168.1.100",
        user_agent="Mozilla/5.0",
    )

    assert audit.id is not None
    assert audit.actor_id == actor_uuid
    assert audit.entity_id == target_uuid
    assert audit.at is not None
    assert hasattr(audit, "updated_at") is False
    assert hasattr(audit, "deleted_at") is False
    assert str(audit) == f"tenant.suspended on tenant:{target_uuid} at {audit.at}"


@pytest.mark.django_db
def test_platform_audit_system_event_null_actor() -> None:
    """System events with actor_id=None are permitted without FK constraints."""
    target_uuid = uuid.uuid4()
    audit = PlatformAudit.objects.create(
        actor_id=None,
        action="system.cleanup",
        entity_type="system",
        entity_id=target_uuid,
    )
    assert audit.id is not None
    assert audit.actor_id is None


@pytest.mark.django_db
def test_platform_factories() -> None:
    """PlatformUserFactory and PlatformAuditFactory build and instantiate
    valid records.
    """
    user = PlatformUserFactory(email="factory_admin@labflow.app")
    assert user.id is not None
    assert user.check_password("SuperAdminPassword123!") is True

    audit = PlatformAuditFactory(action="plan.created")
    assert audit.id is not None
    assert audit.action == "plan.created"
