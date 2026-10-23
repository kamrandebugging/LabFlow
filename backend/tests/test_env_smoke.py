"""
Smoke test proving pytest harness connects to real PostgreSQL and Redis.
Fails fast if services are unreachable or misconfigured.
"""

from __future__ import annotations

import uuid

import pytest
from django.core.cache import cache
from django.db import connection


@pytest.mark.smoke
@pytest.mark.django_db
def test_postgresql_connection_and_vendor() -> None:
    """
    Prove PostgreSQL is active, connection.vendor is 'postgresql',
    and query executes.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS alive, version();")
        row = cursor.fetchone()

    assert row is not None
    assert row[0] == 1
    version_str = str(row[1]).lower()
    assert "postgresql" in version_str
    assert connection.vendor == "postgresql"


@pytest.mark.smoke
def test_redis_cache_write_read_delete() -> None:
    """Prove Redis is reachable, accepts set/get, and deletes test keys."""
    test_key = f"smoke_test_{uuid.uuid4().hex}"
    test_value = {"service": "redis", "status": "verified", "number": 42}

    # Write key
    set_success = cache.set(test_key, test_value, timeout=30)  # type: ignore[func-returns-value]
    assert set_success is not False

    # Read key
    retrieved = cache.get(test_key)
    assert retrieved == test_value

    # Delete key
    delete_success = cache.delete(test_key)
    assert delete_success is True

    # Verify key absence
    assert cache.get(test_key) is None


@pytest.mark.smoke
def test_sqlite_engine_is_not_configured() -> None:
    """Prove that settings.DATABASES does not reference sqlite in any key."""
    from django.conf import settings

    for db_name, db_config in settings.DATABASES.items():
        engine = str(db_config.get("ENGINE", "")).lower()
        assert "sqlite" not in engine, (
            f"Database '{db_name}' configured with banned engine '{engine}'"
        )
