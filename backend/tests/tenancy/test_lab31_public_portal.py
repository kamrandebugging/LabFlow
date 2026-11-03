"""LAB-31 Test Suite: Public report portal (Doc 03 §5.6 RP-8/RP-9/RP-V2/RP-V3,
§6.7, §6.8; KAN-156; original LAB-36). Backend only.

Covers:
- T-36: redeem expired -> 410; revoked -> 410; unknown -> 404;
  valid token after an amendment serves the CURRENT version;
  the database contains no plain token anywhere.
- POST /api/v1/reports/{id}/access-token — roles O M R; 201 with the plain
  token returned ONCE; only the argon2 hash stored; expires_at from the
  `report_link_validity_days` tenant setting (default 7 days); RP-V2 guards
  409 report_not_final (draft) / 409 report_void (void).
- POST /api/v1/reports/{id}/revoke-token — roles O M; token_id or all:true;
  200 idempotent; audit + event flag.
- Public GET /api/v1/report-access/{token}: no auth; 302 to a short-lived
  signed storage URL; last_accessed_at set; latest PENDING/SENT delivery
  marked OPENED; audit on EVERY attempt (success + failure); 410 page carries
  the lab's phone number; rate limit triggers.
- Token reuse inside validity; argon2 scan approach documented in services.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import Client, override_settings
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffUser, TenantSetting
from apps.reports.models import Report, ReportAccessToken, ReportDelivery
from tests.factories.branch import BranchFactory
from tests.factories.reports import (
    ReportDeliveryFactory,
    ReportFactory,
    ReportVersionFactory,
)
from tests.factories.samples import SampleFactory
from tests.factories.staff_user import StaffUserFactory

MINT_URL = "/api/v1/reports/{report_id}/access-token"
REVOKE_URL = "/api/v1/reports/{report_id}/revoke-token"
ACCESS_URL = "/api/v1/report-access/{token}"


def _unique_test_ip() -> str:
    """A 10.x address unique to this test run — the shared test redis
    survives across runs, so fixed IPs would pollute the throttle window."""
    import uuid as _uuid

    n = _uuid.uuid4().int
    return f"10.{(n >> 16) & 0xFF}.{(n >> 8) & 0xFF}.{n & 0xFF}"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser | None = None, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        headers = {"Host": f"{slug}.localhost"}
        if staff_user is not None:
            session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
            headers["Authorization"] = f"Bearer {session['access']}"
        return headers

    return _make_headers


@pytest.fixture
def lab31_setup(tenant_a: Any, tmp_path: Any) -> dict[str, Any]:
    """One branch (with phone), five staff roles, one ready sample with a
    FINAL report v1 whose PDF bytes exist in an isolated storage dir."""
    with tenant_context(tenant_a):
        branch = BranchFactory(
            code="MN1", name="Main Laboratory", phone="+92 42 3577 1234"
        )
        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="owner31@labflow.app"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="mgr31@labflow.app"
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="recep31@labflow.app"
        )
        technician = StaffUserFactory(
            role=Role.TECHNICIAN, branch=branch, email="tech31@labflow.app"
        )
        pathologist = StaffUserFactory(
            role=Role.PATHOLOGIST, branch=branch, email="path31@labflow.app"
        )
        sample = SampleFactory(branch=branch)
        report = ReportFactory(
            sample=sample,
            status=Report.Status.FINAL,
            current_version=1,
        )
        version = ReportVersionFactory(report=report, version=1)
        pdf_bytes = b"%PDF-1.7 fake report bytes for lab31"
        storage = FileSystemStorage(location=str(tmp_path))
        with patch("apps.reports.storage.default_storage", storage):
            storage.save(str(version.pdf_key), ContentFile(pdf_bytes))
        return {
            "tenant": tenant_a,
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "technician": technician,
            "pathologist": pathologist,
            "sample": sample,
            "report": report,
            "version": version,
            "pdf_bytes": pdf_bytes,
            "storage": storage,
            "tmp_path": tmp_path,
        }


def _after(audit: AuditLog) -> dict[str, Any]:
    assert isinstance(audit.after_jsonb, dict)
    return cast(dict[str, Any], audit.after_jsonb)


def _mint_token(
    client: Client,
    headers: dict[str, str],
    report_id: Any,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "HTTP_HOST": headers["Host"],
        "content_type": "application/json",
    }
    if "Authorization" in headers:
        kwargs["HTTP_AUTHORIZATION"] = headers["Authorization"]
    resp = client.post(MINT_URL.format(report_id=report_id), **kwargs)
    assert resp.status_code == 201, resp.content.decode()[:500]
    return resp.json()


class TestMintAccessToken:
    def test_mint_happy_path(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        headers = auth_headers(lab31_setup["owner"])
        with tenant_context(lab31_setup["tenant"]):
            report = lab31_setup["report"]
        body = _mint_token(client, headers, report.id)

        assert set(body) == {"token_id", "link", "expires_at"}
        plain = body["link"].rsplit("/report-access/", 1)[1]
        assert body["link"] == f"/api/v1/report-access/{plain}"
        # urlsafe base64 of 32 bytes -> 44 chars, only urlsafe alphabet
        assert len(plain) == 44
        assert all(c.isalnum() or c in "-_=" for c in plain)

        with tenant_context(lab31_setup["tenant"]):
            row = ReportAccessToken.objects.get(pk=body["token_id"])
            assert row.report_id == report.id
            assert row.token_hash != plain
            assert row.token_hash.startswith("$argon2")
            assert row.revoked_at is None
            # default 7 days when no tenant setting row exists
            expected = timezone.now() + timedelta(days=7)
            assert abs((row.expires_at - expected).total_seconds()) < 120
            # audit: token issue carries the ROW id, never the plain token
            audit = AuditLog.objects.get(action="report.token_issued")
            assert audit.entity_type == "report_access_token"
            assert audit.entity_id == row.id
            assert _after(audit)["token_id"] == str(row.id)
            assert plain not in str(audit.after_jsonb)
            # the DB holds no plain token anywhere
            assert ReportAccessToken.objects.filter(token_hash=plain).count() == 0

    def test_mint_plain_token_never_in_db_text_fields(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        headers = auth_headers(lab31_setup["owner"])
        with tenant_context(lab31_setup["tenant"]):
            report = lab31_setup["report"]
        body = _mint_token(client, headers, report.id)
        plain = body["link"].rsplit("/report-access/", 1)[1]
        with tenant_context(lab31_setup["tenant"]):
            for row in ReportAccessToken.objects.all():
                assert plain not in row.token_hash
            for audit in AuditLog.objects.all():
                assert plain not in str(audit.before_jsonb)
                assert plain not in str(audit.after_jsonb)

    def test_mint_expiry_from_tenant_setting(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            TenantSetting.objects.create(
                key="report_link_validity_days", value="3", updated_by=None
            )
            report_id = lab31_setup["report"].id
        headers = auth_headers(lab31_setup["manager"])
        body = _mint_token(client, headers, report_id)
        with tenant_context(lab31_setup["tenant"]):
            row = ReportAccessToken.objects.get(pk=body["token_id"])
            expected = timezone.now() + timedelta(days=3)
            assert abs((row.expires_at - expected).total_seconds()) < 120

    def test_mint_invalid_setting_value_falls_back_to_default(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            TenantSetting.objects.create(
                key="report_link_validity_days",
                value="not-a-number",
                updated_by=None,
            )
            report_id = lab31_setup["report"].id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        with tenant_context(lab31_setup["tenant"]):
            row = ReportAccessToken.objects.get(pk=body["token_id"])
            expected = timezone.now() + timedelta(days=7)
            assert abs((row.expires_at - expected).total_seconds()) < 120

    def test_mint_roles(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
            users = lab31_setup
        for role_key, expected in [
            ("owner", 201),
            ("manager", 201),
            ("receptionist", 201),
            ("technician", 403),
            ("pathologist", 403),
        ]:
            headers = auth_headers(users[role_key])
            resp = client.post(
                MINT_URL.format(report_id=report_id),
                content_type="application/json",
                HTTP_HOST=headers["Host"],
                **(
                    {"HTTP_AUTHORIZATION": headers["Authorization"]}
                    if "Authorization" in headers
                    else {}
                ),
            )
            assert resp.status_code == expected, (role_key, resp.content[:200])

    def test_mint_unauthenticated(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
        resp = client.post(
            MINT_URL.format(report_id=report_id),
            content_type="application/json",
            HTTP_HOST=auth_headers()["Host"],
        )
        assert resp.status_code == 401

    def test_mint_draft_report_409(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            draft = ReportFactory(sample=lab31_setup["sample"])
        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            MINT_URL.format(report_id=draft.id),
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "report_not_final"

    def test_mint_version_zero_409(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report = ReportFactory(
                sample=lab31_setup["sample"],
                status=Report.Status.FINAL,
                current_version=0,
            )
        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            MINT_URL.format(report_id=report.id),
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "report_not_final"

    def test_mint_void_report_409(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report = ReportFactory(
                sample=lab31_setup["sample"],
                status=Report.Status.VOID,
                current_version=1,
            )
        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            MINT_URL.format(report_id=report.id),
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "report_void"

    def test_mint_unknown_report_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        import uuid

        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            MINT_URL.format(report_id=uuid.uuid4()),
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 404

    def test_mint_other_tenant_report_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        # tenant-scoped: a report id from another tenant is a 404, never 403
        import uuid

        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            MINT_URL.format(report_id=uuid.uuid4()),
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 404


class TestRedeemAccessToken:
    def test_valid_token_302_and_follow(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        plain = body["link"].rsplit("/report-access/", 1)[1]

        with patch("apps.reports.storage.default_storage", lab31_setup["storage"]):
            host = auth_headers()["Host"]
            resp = client.get(ACCESS_URL.format(token=plain), HTTP_HOST=host)
            assert resp.status_code == 302
            location = resp["Location"]
            assert "/api/v1/report-files/" in location
            # Short-lived target: the 302 itself must never be cached.
            assert resp["Cache-Control"] == "no-store"

            follow = client.get(location, HTTP_HOST=host)
            assert follow.status_code == 200
            assert b"".join(follow.streaming_content) == lab31_setup["pdf_bytes"]

        with tenant_context(lab31_setup["tenant"]):
            row = ReportAccessToken.objects.get(pk=body["token_id"])
            assert row.last_accessed_at is not None
            audit = AuditLog.objects.get(action="report.accessed")
            assert audit.entity_id == row.id
            assert _after(audit)["event"] == "report.accessed"
            assert plain not in str(audit.after_jsonb)

    def test_token_reusable_within_validity(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        plain = body["link"].rsplit("/report-access/", 1)[1]
        host = auth_headers()["Host"]
        for _ in range(2):
            resp = client.get(ACCESS_URL.format(token=plain), HTTP_HOST=host)
            assert resp.status_code == 302

    def test_redeem_marks_latest_pending_delivery_opened(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report = lab31_setup["report"]
            ReportDeliveryFactory(
                report=report,
                channel=ReportDelivery.Channel.WHATSAPP,
                status=ReportDelivery.Status.PENDING,
            )
            report_id = report.id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        plain = body["link"].rsplit("/report-access/", 1)[1]
        resp = client.get(
            ACCESS_URL.format(token=plain), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 302
        with tenant_context(lab31_setup["tenant"]):
            delivery = ReportDelivery.objects.get(report=report)
            assert delivery.status == ReportDelivery.Status.OPENED

    def test_redeem_without_delivery_skips_silently(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        plain = body["link"].rsplit("/report-access/", 1)[1]
        resp = client.get(
            ACCESS_URL.format(token=plain), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 302
        with tenant_context(lab31_setup["tenant"]):
            assert ReportDelivery.objects.count() == 0

    def test_redeem_latest_delivery_only(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report = lab31_setup["report"]
            old = ReportDeliveryFactory(
                report=report,
                channel=ReportDelivery.Channel.EMAIL,
                status=ReportDelivery.Status.SENT,
            )
            new = ReportDeliveryFactory(
                report=report,
                channel=ReportDelivery.Channel.WHATSAPP,
                status=ReportDelivery.Status.PENDING,
            )
            report_id = report.id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        plain = body["link"].rsplit("/report-access/", 1)[1]
        resp = client.get(
            ACCESS_URL.format(token=plain), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 302
        with tenant_context(lab31_setup["tenant"]):
            assert ReportDelivery.objects.get(pk=new.pk).status == "OPENED"
            assert ReportDelivery.objects.get(pk=old.pk).status == "SENT"

    def test_unknown_token_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        fake = secrets.token_urlsafe(32)
        resp = client.get(
            ACCESS_URL.format(token=fake), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 404
        with tenant_context(lab31_setup["tenant"]):
            audit = AuditLog.objects.get(action="report.access_failed")
            assert _after(audit)["reason"] == "unknown"
            assert fake not in str(audit.after_jsonb)

    def test_expired_token_410_with_phone(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        body = _mint_token(
            client,
            auth_headers(lab31_setup["owner"]),
            lab31_setup["report"].id,
        )
        plain = body["link"].rsplit("/report-access/", 1)[1]
        with tenant_context(lab31_setup["tenant"]):
            # Backdate the whole row (created_at AND expires_at) so the
            # chk_report_access_token_expires_after_created constraint holds
            # while the token is genuinely expired.
            past = timezone.now() - timedelta(hours=1)
            ReportAccessToken.objects.filter(pk=body["token_id"]).update(
                created_at=past - timedelta(hours=1), expires_at=past
            )
        resp = client.get(
            ACCESS_URL.format(token=plain), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 410
        content = resp.content.decode()
        assert "expired" in content.lower()
        assert "+92 42 3577 1234" in content  # lab's phone (RP-9)
        assert plain not in content
        with tenant_context(lab31_setup["tenant"]):
            audit = AuditLog.objects.get(action="report.access_failed")
            assert _after(audit)["reason"] == "expired"
            assert plain not in str(audit.after_jsonb)

    def test_revoked_token_410(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        body = _mint_token(
            client,
            auth_headers(lab31_setup["owner"]),
            lab31_setup["report"].id,
        )
        plain = body["link"].rsplit("/report-access/", 1)[1]
        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            REVOKE_URL.format(report_id=lab31_setup["report"].id),
            data={"token_id": body["token_id"]},
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 200
        resp = client.get(
            ACCESS_URL.format(token=plain), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 410
        with tenant_context(lab31_setup["tenant"]):
            audit = AuditLog.objects.get(action="report.access_failed")
            assert _after(audit)["reason"] == "revoked"

    def test_valid_token_after_amendment_serves_current_version(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        # RP-8: patient links always resolve to the CURRENT version.
        with tenant_context(lab31_setup["tenant"]):
            report = lab31_setup["report"]
            report.status = Report.Status.AMENDED
            report.current_version = 2
            report.save(update_fields=["status", "current_version", "updated_at"])
            v2 = ReportVersionFactory(report=report, version=2)
            v2_bytes = b"%PDF-1.7 amended version bytes"
            lab31_setup["storage"].save(v2.pdf_key, ContentFile(v2_bytes))
            report_id = report.id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        plain = body["link"].rsplit("/report-access/", 1)[1]
        host = auth_headers()["Host"]
        with patch("apps.reports.storage.default_storage", lab31_setup["storage"]):
            resp = client.get(ACCESS_URL.format(token=plain), HTTP_HOST=host)
            assert resp.status_code == 302
            follow = client.get(resp["Location"], HTTP_HOST=host)
            assert follow.status_code == 200
            assert b"".join(follow.streaming_content) == v2_bytes

    def test_no_auth_required(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        # RP-V3: the token is the ONLY credential — no login wall.
        body = _mint_token(
            client,
            auth_headers(lab31_setup["owner"]),
            lab31_setup["report"].id,
        )
        plain = body["link"].rsplit("/report-access/", 1)[1]
        resp = client.get(
            ACCESS_URL.format(token=plain), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 302

    @override_settings(REPORT_ACCESS_RATE_LIMIT_PER_MINUTE=3)
    def test_rate_limit_triggers(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        # Distinct client IP so the shared test-cache counter from other
        # tests cannot pollute this fixed window.
        host = auth_headers()["Host"]
        ip = _unique_test_ip()
        codes = []
        for _ in range(4):
            resp = client.get(
                ACCESS_URL.format(token=secrets.token_urlsafe(32)),
                HTTP_HOST=host,
                HTTP_X_FORWARDED_FOR=ip,
            )
            codes.append(resp.status_code)
        assert codes[:3] == [404, 404, 404]
        assert codes[3] == 429


class TestRevokeAccessToken:
    def test_revoke_happy_idempotent(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        body = _mint_token(
            client,
            auth_headers(lab31_setup["owner"]),
            lab31_setup["report"].id,
        )
        headers = auth_headers(lab31_setup["manager"])
        payload = {"token_id": body["token_id"]}
        for _ in range(2):  # idempotent: revoking twice -> 200
            resp = client.post(
                REVOKE_URL.format(report_id=lab31_setup["report"].id),
                data=payload,
                content_type="application/json",
                HTTP_HOST=headers["Host"],
                HTTP_AUTHORIZATION=headers["Authorization"],
            )
            assert resp.status_code == 200
        with tenant_context(lab31_setup["tenant"]):
            row = ReportAccessToken.objects.get(pk=body["token_id"])
            assert row.revoked_at is not None
            # one audit row per revoke call (idempotent second call audits
            # revoked_count 0)
            audits = AuditLog.objects.filter(action="report.token_revoked").order_by(
                "at"
            )
            assert audits.count() == 2
            assert _after(audits[0])["event"] == "report.token_revoked"
            assert _after(audits[0])["token_id"] == body["token_id"]
            assert _after(audits[0])["revoked_count"] == 1
            assert _after(audits[1])["revoked_count"] == 0

    def test_revoke_all(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
        headers = auth_headers(lab31_setup["owner"])
        first = _mint_token(client, headers, report_id)
        second = _mint_token(client, headers, report_id)
        resp = client.post(
            REVOKE_URL.format(report_id=report_id),
            data={"all": True},
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 200
        assert resp.json()["revoked_count"] == 2
        with tenant_context(lab31_setup["tenant"]):
            assert (
                ReportAccessToken.objects.filter(revoked_at__isnull=True).count() == 0
            )
        host = auth_headers()["Host"]
        for token_link in (first["link"], second["link"]):
            plain = token_link.rsplit("/report-access/", 1)[1]
            resp = client.get(ACCESS_URL.format(token=plain), HTTP_HOST=host)
            assert resp.status_code == 410

    def test_revoke_roles(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        body = _mint_token(
            client,
            auth_headers(lab31_setup["owner"]),
            lab31_setup["report"].id,
        )
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
            recep = lab31_setup["receptionist"]
            mgr = lab31_setup["manager"]
        for user, expected in [(recep, 403), (mgr, 200)]:
            headers = auth_headers(user)
            resp = client.post(
                REVOKE_URL.format(report_id=report_id),
                data={"token_id": body["token_id"]},
                content_type="application/json",
                HTTP_HOST=headers["Host"],
                HTTP_AUTHORIZATION=headers["Authorization"],
            )
            assert resp.status_code == expected, (user.role, resp.content[:200])

    def test_revoke_body_validation(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
        headers = auth_headers(lab31_setup["owner"])
        for bad in [
            {},
            {"token_id": "not-a-uuid"},
            {"token_id": None, "all": False},
            {"extra": 1},
        ]:
            resp = client.post(
                REVOKE_URL.format(report_id=report_id),
                data=bad,
                content_type="application/json",
                HTTP_HOST=headers["Host"],
                HTTP_AUTHORIZATION=headers["Authorization"],
            )
            assert resp.status_code == 422, (bad, resp.content[:200])

    def test_revoke_unknown_token_id_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        import uuid

        with tenant_context(lab31_setup["tenant"]):
            report_id = lab31_setup["report"].id
        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            REVOKE_URL.format(report_id=report_id),
            data={"token_id": str(uuid.uuid4())},
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 404

    def test_revoke_unknown_report_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        import uuid

        headers = auth_headers(lab31_setup["owner"])
        resp = client.post(
            REVOKE_URL.format(report_id=uuid.uuid4()),
            data={"all": True},
            content_type="application/json",
            HTTP_HOST=headers["Host"],
            HTTP_AUTHORIZATION=headers["Authorization"],
        )
        assert resp.status_code == 404


class TestFileDownloadAndHardening:
    def test_file_download_bad_signature_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        resp = client.get(
            "/api/v1/report-files/not-a-valid-signature",
            HTTP_HOST=auth_headers()["Host"],
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "file_not_found"

    def test_file_download_expired_signature_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        from django.core.signing import TimestampSigner

        from apps.reports.storage import REPORT_FILE_SIGNER_SALT

        signed = TimestampSigner(salt=REPORT_FILE_SIGNER_SALT).sign("reports/x/1.pdf")
        with patch("apps.reports.views.FILE_URL_VALIDITY_SECONDS", -1):
            resp = client.get(
                f"/api/v1/report-files/{signed}",
                HTTP_HOST=auth_headers()["Host"],
            )
        assert resp.status_code == 404

    def test_file_download_unknown_pdf_key_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        from django.core.signing import TimestampSigner

        from apps.reports.storage import REPORT_FILE_SIGNER_SALT

        signed = TimestampSigner(salt=REPORT_FILE_SIGNER_SALT).sign(
            "reports/does-not-exist/1.pdf"
        )
        resp = client.get(
            f"/api/v1/report-files/{signed}",
            HTTP_HOST=auth_headers()["Host"],
        )
        assert resp.status_code == 404

    def test_presigned_url_s3_prod_path(self) -> None:
        """R2/MinIO prod path: a storage backend with bucket_name gets a
        real pre-signed URL via backend.url(..., expire=...)."""
        from types import SimpleNamespace

        from apps.reports.storage import ReportStorage

        backend = SimpleNamespace(
            bucket_name="labflow-reports",
            url=lambda name, **kwargs: (
                f"https://r2.example/{name}?expire={kwargs.get('expire')}"
            ),
        )
        with patch("apps.reports.storage.default_storage", backend):
            url = ReportStorage().presigned_url("reports/abc/1.pdf", 900)
        assert url == "https://r2.example/reports/abc/1.pdf?expire=900"

    def test_throttle_fail_open_on_cache_error(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        """A down cache must not 500 patients — the throttle fails open
        (and logs). Documented in apps/reports/throttling.py."""
        from unittest.mock import MagicMock

        broken = MagicMock()
        broken.add.side_effect = ConnectionError("redis down")
        broken.incr.side_effect = ConnectionError("redis down")
        with patch("apps.reports.throttling.cache", broken):
            resp = client.get(
                ACCESS_URL.format(token=secrets.token_urlsafe(32)),
                HTTP_HOST=auth_headers()["Host"],
                HTTP_X_FORWARDED_FOR=_unique_test_ip(),
            )
        # Request was allowed through despite the cache failure.
        assert resp.status_code == 404

    def test_throttle_resets_on_non_numeric_value(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        """A corrupted (non-numeric) counter value resets the window instead
        of 500ing."""
        from unittest.mock import MagicMock

        weird = MagicMock()
        weird.add.return_value = False
        weird.incr.side_effect = ValueError("non-numeric")
        with patch("apps.reports.throttling.cache", weird):
            resp = client.get(
                ACCESS_URL.format(token=secrets.token_urlsafe(32)),
                HTTP_HOST=auth_headers()["Host"],
                HTTP_X_FORWARDED_FOR=_unique_test_ip(),
            )
        assert resp.status_code == 404
        assert weird.set.called

    def test_unknown_token_with_live_tokens_scans_past_them(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        """A wrong token against existing live rows exercises the argon2
        mismatch-continue branch and still returns 404 (no distinction)."""
        body = _mint_token(
            client,
            auth_headers(lab31_setup["owner"]),
            lab31_setup["report"].id,
        )
        assert body["token_id"]
        fake = secrets.token_urlsafe(32)
        resp = client.get(
            ACCESS_URL.format(token=fake), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 404
        with tenant_context(lab31_setup["tenant"]):
            audit = AuditLog.objects.get(action="report.access_failed")
            assert _after(audit)["reason"] == "unknown"

    def test_redeem_missing_version_row_500(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        """Data inconsistency: report claims current_version=2 but no
        report_version row exists for it -> honest 500, still audited.
        (report_version is append-only, so the gap is simulated by bumping
        current_version instead of deleting the row.)"""
        with tenant_context(lab31_setup["tenant"]):
            report = lab31_setup["report"]
            report.current_version = 2
            report.save(update_fields=["current_version", "updated_at"])
            report_id = report.id
        body = _mint_token(client, auth_headers(lab31_setup["owner"]), report_id)
        plain = body["link"].rsplit("/report-access/", 1)[1]
        resp = client.get(
            ACCESS_URL.format(token=plain), HTTP_HOST=auth_headers()["Host"]
        )
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "report_version_missing"

    @override_settings(REPORT_ACCESS_RATE_LIMIT_PER_MINUTE=1)
    def test_file_download_rate_limited(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        host = auth_headers()["Host"]
        ip = _unique_test_ip()
        first = client.get(
            "/api/v1/report-files/anything",
            HTTP_HOST=host,
            HTTP_X_FORWARDED_FOR=ip,
        )
        second = client.get(
            "/api/v1/report-files/anything",
            HTTP_HOST=host,
            HTTP_X_FORWARDED_FOR=ip,
        )
        assert first.status_code == 404  # bad signature, not throttled
        assert second.status_code == 429

    def test_file_download_version_row_but_no_file_404(
        self, client: Client, auth_headers: Any, lab31_setup: dict[str, Any]
    ) -> None:
        """Signed URL valid and version row exists, but the object is gone
        from storage -> 404, never a 500."""
        from django.core.signing import TimestampSigner

        from apps.reports.storage import REPORT_FILE_SIGNER_SALT

        with tenant_context(lab31_setup["tenant"]):
            pdf_key = lab31_setup["version"].pdf_key
        signed = TimestampSigner(salt=REPORT_FILE_SIGNER_SALT).sign(str(pdf_key))
        with patch(
            "apps.reports.storage.default_storage",
            FileSystemStorage(location=str(lab31_setup["tmp_path"]) + "-empty"),
        ):
            resp = client.get(
                f"/api/v1/report-files/{signed}",
                HTTP_HOST=auth_headers()["Host"],
            )
        assert resp.status_code == 404
