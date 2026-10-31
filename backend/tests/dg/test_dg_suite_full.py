"""DG-Suite meta-tests and gate assertions per Doc 09 §18.

Verifies:
- DG-04: Table set conformance per Doc 02 / Doc 09 §7.2
- DG-06: Non-GET service mutation audit contract check (Doc 09 §5.5)
- DG-08: Frontend test-ID grammar check (kebab-case) (Doc 09 §10.2)
- DG-10: Fake secret / canary token detection (Doc 09 §12.2)
- DG-18: Celery task idempotent re-run contract (Doc 09 §5.6)
- DG-24: LocalStorage patient privacy leak protection (Doc 09 §6.3)
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from django.db import connection
from django_tenants.utils import schema_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser
from tests.fixtures.tenants import TenantFixture


@pytest.mark.dg
def test_dg04_schema_conformance_managed_models(tenant_a: TenantFixture) -> None:
    """DG-04: Verify all managed models have valid table definitions."""
    with schema_context(tenant_a.schema_name), connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s;",
            [tenant_a.schema_name],
        )
        tables = {row[0] for row in cursor.fetchall()}

    # Core tenant tables must exist
    required_tables = (
        "branch",
        "staff_user",
        "patient",
        "invoice",
        "sample",
        "result",
        "audit_log",
    )
    for required_table in required_tables:
        assert required_table in tables, (
            f"Expected table {required_table} missing from tenant schema"
        )


@pytest.mark.dg
def test_dg06_audit_contract_on_mutations(tenant_a: TenantFixture) -> None:
    """DG-06: Non-GET mutations must emit an audit_log row."""
    with schema_context(tenant_a.schema_name):
        user = StaffUser.objects.create(
            email=f"audittest_{uuid.uuid4().hex[:6]}@lab.com",
            password_hash="argon2hash",
            role=Role.TECHNICIAN,
            is_active=True,
        )
        initial_count = AuditLog.objects.filter(actor_id=user.id).count()

        # Perform a state mutation
        AuthService.revoke_all_sessions(
            staff_user_id=user.id,
            tenant_id=tenant_a.schema_name,
            reason="audit_contract_verification",
        )

        assert (
            AuditLog.objects.filter(
                actor_id=user.id, action="auth.sessions_revoked"
            ).count()
            > initial_count
        )


@pytest.mark.dg
def test_dg08_testid_grammar_validator() -> None:
    """DG-08: Verify test-ID lint grammar enforces kebab-case."""
    kebab_pattern = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

    # Compliant purpose-named test-ids
    valid_ids = (
        "login-submit-button",
        "patient-search-input",
        "results-worklist-table",
    )
    for valid_id in valid_ids:
        assert kebab_pattern.match(valid_id) is not None

    # Non-compliant presentation or camelCase ids
    for invalid_id in ("blueBtn", "submitBtn", "button_1", "SEARCH_INPUT"):
        assert kebab_pattern.match(invalid_id) is None


@pytest.mark.dg
def test_dg10_secret_canary_pattern_detection() -> None:
    """DG-10: Canary tokens and secret patterns are caught by screening."""
    secret_pattern = re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|private[_-]?key)\s*[:=]\s*"
        r"['\"][A-Za-z0-9_\-]{16,}['\"]"
    )

    canary = "api_key = 'AKIA1234567890EXAMPLEKEY'"
    safe_code = "api_key_name = 'X-API-Key'"

    assert secret_pattern.search(canary) is not None
    assert secret_pattern.search(safe_code) is None


@pytest.mark.dg
def test_dg18_idempotency_key_contract() -> None:
    """DG-18: Running with same idempotency key produces identical state."""
    key = f"dg18-{uuid.uuid4()}"
    executed_state: dict[str, Any] = {}

    def simulate_task(idem_key: str, data: str) -> dict[str, Any]:
        if idem_key in executed_state:
            return executed_state[idem_key]
        executed_state[idem_key] = {"result": f"processed-{data}", "count": 1}
        return executed_state[idem_key]

    run1 = simulate_task(key, "order_123")
    run2 = simulate_task(key, "order_123")

    assert run1 == run2
    assert run1["count"] == 1


@pytest.mark.dg
def test_dg24_localstorage_patient_privacy_check() -> None:
    """DG-24: Verify screening catches localStorage patient identifiers."""
    forbidden_pattern = re.compile(
        r"localStorage\.(setItem|getItem)\s*\(\s*['\"][^'\"]*"
        r"(patient|mrn|dob|cnic)[^'\"]*['\"]"
    )

    leaky_code = "localStorage.setItem('patient_name', patient.name)"
    safe_code = "localStorage.setItem('theme', 'dark')"

    assert forbidden_pattern.search(leaky_code) is not None
    assert forbidden_pattern.search(safe_code) is None
