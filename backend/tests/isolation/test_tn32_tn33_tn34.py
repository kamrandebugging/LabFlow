"""TN-32 / TN-33 / TN-34 — named cross-tenant isolation scenarios (Doc 04 §18).

These sit ON TOP of the generated per-model suite (TN-31, §13.7): tokens
across hosts, callback slug mismatch, cache poisoning, worker context
reset, and the PgBouncer gate.
"""

from __future__ import annotations

import ast
import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django_tenants.utils import schema_context, tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role
from apps.reports.models import Report
from tests.factories.branch import BranchFactory
from tests.factories.reports import ReportFactory
from tests.factories.samples import SampleFactory
from tests.factories.staff_user import StaffUserFactory

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _unique_test_ip() -> str:
    n = uuid.uuid4().int
    return f"10.{(n >> 16) & 0xFF}.{(n >> 8) & 0xFF}.{n & 0xFF}"


def _auth_headers(user: Any, tenant_id: str = "tenant_a") -> dict[str, str]:
    slug = str(tenant_id).replace("_", "-")
    session = AuthService.create_session(user=user, tenant_id=tenant_id)
    return {
        "Authorization": f"Bearer {session['access']}",
        "Host": f"{slug}.localhost",
    }


# ---------------------------------------------------------------------------
# TN-32 — tokens across hosts, callback slug mismatch, missing-slug tasks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.isolation
class TestTN32TokensAcrossHosts:
    def test_report_token_on_other_host_404(self, tenant_a: Any, tenant_b: Any) -> None:
        """TN-32: A's report token presented on B's host -> 404."""
        with tenant_context(tenant_a):
            branch = BranchFactory(code="TNX", name="TN32 Branch")
            owner = StaffUserFactory(
                role=Role.OWNER, branch=None, email="tn32_owner@labflow.app"
            )
            sample = SampleFactory(branch=branch)
            report = ReportFactory(
                sample=sample, status=Report.Status.FINAL, current_version=1
            )
            headers = _auth_headers(owner, "tenant_a")
            resp = Client().post(
                f"/api/v1/reports/{report.id}/access-token",
                HTTP_HOST=headers["Host"],
                HTTP_AUTHORIZATION=headers["Authorization"],
                content_type="application/json",
            )
            assert resp.status_code == 201, resp.content.decode()[:400]
            plain = resp.json()["link"].rsplit("/", 1)[-1]

            # Positive control: the token resolves inside A's schema.
            from apps.reports.services import ReportAccessService

            row, reason = ReportAccessService._find_token(plain)
            assert row is not None and reason is None

        # On B's host the same token is unknown -> 404 JSON (token_not_found).
        resp = Client().get(
            f"/api/v1/report-access/{plain}",
            HTTP_HOST="tenant-b.localhost",
            REMOTE_ADDR=_unique_test_ip(),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "token_not_found"

    @pytest.mark.skip(
        reason=(
            "No inbound n8n callback endpoint exists in v1 — the automation "
            "app is outbound-only (webhook_delivery rows, Doc 06). The "
            "slug-mismatch 403 scenario applies when an inbound callback "
            "receiver is built."
        )
    )
    def test_n8n_callback_slug_mismatch_403(self) -> None:
        """TN-32: n8n callback slug mismatch -> 403 (no endpoint in v1)."""

    def test_task_with_missing_slug_raises_and_writes_nothing(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        """TN-32: a task with a missing/unknown slug raises loudly and writes
        nothing — never silently in the worker's current context (Doc 04 §13.2)."""
        from django.db.utils import ProgrammingError

        from apps.reports.models import ReportVersion
        from apps.reports.tasks import generate_pdf_task

        with tenant_context(tenant_a):
            before_a = ReportVersion.objects.count()
        with tenant_context(tenant_b):
            before_b = ReportVersion.objects.count()

        with pytest.raises(ProgrammingError):
            generate_pdf_task("tenant_missing_nope", str(uuid.uuid4()), None, 1)

        with tenant_context(tenant_a):
            assert ReportVersion.objects.count() == before_a
        with tenant_context(tenant_b):
            assert ReportVersion.objects.count() == before_b


# ---------------------------------------------------------------------------
# TN-33 — context reset, cache poisoning
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.isolation
class TestTN33ContextResetAndCache:
    def test_task_raising_mid_work_leaves_worker_on_public_schema(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        """TN-33: a task raising mid-work leaves the worker on the public
        schema (F-13); the next task, entering its own tenant, sees only
        its own rows."""
        from apps.accounts.models import StaffUser

        with tenant_context(tenant_a):
            user_a = StaffUserFactory(email="tn33_a@labflow.app")
        with tenant_context(tenant_b):
            user_b = StaffUserFactory(email="tn33_b@labflow.app")

        # Simulate a tenant task raising mid-work.
        with (
            pytest.raises(RuntimeError, match="boom mid-work"),
            schema_context("tenant_a"),
        ):
            assert StaffUser.objects.filter(pk=user_a.pk).exists()
            raise RuntimeError("boom mid-work")

        # The worker is back on the public schema — a surviving context
        # would be the next task's leak.
        assert connection.schema_name == "public"

        # The next task sees only its own tenant's rows.
        with schema_context("tenant_b"):
            assert StaffUser.objects.filter(pk=user_b.pk).exists()
            assert not StaffUser.objects.filter(pk=user_a.pk).exists()
        with schema_context("tenant_a"):
            assert StaffUser.objects.filter(pk=user_a.pk).exists()
            assert not StaffUser.objects.filter(pk=user_b.pk).exists()

    def test_cache_value_invisible_under_other_tenant_prefix(self) -> None:
        """TN-33: A's cache value is invisible under B's key prefix."""
        from apps.accounts.session_registry import _sessions_key

        user_id = uuid.uuid4()
        key_a = _sessions_key("tenant_a", user_id)
        key_b = _sessions_key("tenant_b", user_id)
        assert key_a != key_b

        cache.set(key_a, "secret-a", timeout=60)
        try:
            assert cache.get(key_a) == "secret-a"
            assert cache.get(key_b) is None
        finally:
            cache.delete(key_a)

    def test_raw_cache_import_banned_outside_allow_list(self) -> None:
        """TN-33: raw cache access is banned mechanically — a CI rule fails
        any build importing the raw client outside the wrapper/allow-list
        (Doc 04 §13.3). Implemented as a test so CI (pytest) enforces it."""
        offenders: list[str] = []
        for path in (BACKEND_ROOT / "apps").rglob("*.py"):
            if "__pycache__" in path.parts or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                raw = False
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "django.core.cache"
                ):
                    raw = True
                if isinstance(node, ast.Import) and any(
                    alias.name.startswith("django.core.cache") for alias in node.names
                ):
                    raw = True
                if raw:
                    rel = str(path.relative_to(BACKEND_ROOT))
                    if rel not in RAW_CACHE_ALLOWLIST:
                        offenders.append(rel)
        assert not offenders, (
            "Raw django.core.cache imports outside the allow-list "
            f"(Doc 04 §13.3): {offenders}"
        )


# Doc 04 §13.3: raw cache access from tenant apps is banned; the two
# pre-existing call sites are allow-listed with written reasons, reviewed
# like a schema change. New raw imports fail test_raw_cache_import_banned...
RAW_CACHE_ALLOWLIST: dict[str, str] = {
    "apps/platform/auth_service.py": (
        "Apex-only platform auth state (login/TOTP challenges, denylist) — "
        "never keyed per tenant schema, so no tenant can collide on these keys."
    ),
    "apps/platform/platform_session_registry.py": (
        "Apex-only platform operator sessions keyed by user id; the platform "
        "surface has no tenant schema context to segment on."
    ),
    "apps/platform/views_metrics.py": (
        "The 60s overview cache is a single apex-wide snapshot aggregated from "
        "the public schema only."
    ),
    "apps/platform/access.py": (
        "Access-mode keys are tenant-segmented by construction "
        "(tenant:<slug>:access-mode, 60s TTL). Migration to a "
        "tenant:-prefixed wrapper is tracked follow-up work, not this ticket."
    ),
    "apps/accounts/auth_service.py": (
        "TOTP/login-attempt keys already carry explicit tenant_id segments "
        "(auth:totp_pending, per-tenant attempt keys). Migration to a "
        "tenant:-prefixed wrapper is tracked follow-up work, not this ticket."
    ),
    "apps/accounts/session_registry.py": (
        "Session revocation/denylist keys are tenant-segmented by "
        "construction (_sessions_key includes tenant_id). Migration to a "
        "tenant:-prefixed wrapper is tracked follow-up work, not this ticket."
    ),
    "apps/accounts/throttling.py": (
        "Login throttle keys are segmented per (tenant_id, email) and "
        "(tenant_id, IP) by construction. Migration to a tenant:-prefixed "
        "wrapper is tracked follow-up work, not this ticket."
    ),
    "apps/reports/throttling.py": (
        "Report-access rate-limit keys are scoped per token/IP by "
        "construction (labflow:rl:<scope>:<ip>). Migration to a "
        "tenant:-prefixed wrapper is tracked follow-up work, not this ticket."
    ),
    "apps/platform/tls.py": (
        "TLS-ask cache keys are platform-scope (platform keys per Doc 04 "
        "§13.3), not tenant data. Migration to a platform:-prefixed wrapper "
        "is tracked follow-up work, not this ticket."
    ),
}


# ---------------------------------------------------------------------------
# TN-34 — PgBouncer gate (staging, when enabled)
# ---------------------------------------------------------------------------

PGBOUNCER_GATE_ENABLED = os.environ.get("LABFLOW_PGBOUNCER_GATE") == "1"


@pytest.mark.skipif(
    not PGBOUNCER_GATE_ENABLED,
    reason="PgBouncer gate runs on staging when enabled (Doc 04 §13.6, TN-34).",
)
@pytest.mark.django_db
@pytest.mark.isolation
class TestTN34PgBouncerGate:
    def test_interleaved_tenants_on_one_backend_stay_isolated(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        """TN-34: two tenants interleaved over one pooled backend connection
        each see only their own schema. Tenant switching is
        transaction-scoped (SET LOCAL / search_path reset, F-5)."""
        from apps.accounts.models import StaffUser

        with tenant_context(tenant_a):
            user_a = StaffUserFactory(email="tn34_a@labflow.app")
        with tenant_context(tenant_b):
            user_b = StaffUserFactory(email="tn34_b@labflow.app")

        connection.ensure_connection()
        for _ in range(2):  # interleave twice on the same backend
            with schema_context("tenant_a"):
                assert StaffUser.objects.filter(pk=user_a.pk).exists()
                assert not StaffUser.objects.filter(pk=user_b.pk).exists()
            with schema_context("tenant_b"):
                assert StaffUser.objects.filter(pk=user_b.pk).exists()
                assert not StaffUser.objects.filter(pk=user_a.pk).exists()
        # NOTE: "migrations run direct only" is a deploy-script rule
        # (provisioning connects directly, never through the pool); it has
        # no in-app code path to test here.
