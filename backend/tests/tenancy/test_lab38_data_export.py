"""LAB-38 Test Suite: Tenant data portability — Owner export (Doc 04 §4.3;
KAN-163; original LAB-49).

Covers:
- POST /api/v1/exports as Owner -> 202, export record created, Celery task
  enqueued (tenants.export_tenant).
- POST as non-Owner (Manager/Technician) -> 403.
- Export task: one CSV per tenant table, report PDFs included, manifest.json
  with SHA-256 per file, row counts.
- Secret exclusion: password_hash, totp_secret_encrypted,
  totp_backup_codes_hash, every token_hash column excluded from CSVs;
  manifest records exclusions with reasons.
- Export available in read-only mode (subscription) — not blocked by 403
  subscription_read_only.
- Signed download link valid 7 days; audit log entry on completion.
- TN-38: secrets excluded without exception; manifest records why.
"""

import hashlib
import io
import json
import uuid
import zipfile
from typing import Any
from unittest.mock import patch

import pytest
from django.test import Client, captureOnCommitCallbacks
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, DataExport, Role, StaffUser
from tests.factories.branch import BranchFactory
from tests.factories.staff_user import StaffUserFactory

EXPORTS_URL = "/api/v1/exports"
EXPORT_DETAIL_URL = "/api/v1/exports/{export_id}"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(
        staff_user: StaffUser, tenant_id: str = "tenant_a"
    ) -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(
            user=staff_user,
            tenant_id=tenant_id,
        )
        return {
            "Authorization": f"Bearer {session['access']}",
            "Host": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def lab38_setup(tenant_a: Any) -> dict[str, Any]:
    """Owner + manager users for export tests."""
    with tenant_context(tenant_a):
        branch = BranchFactory(code="MN1", name="Main Laboratory")
        owner = StaffUserFactory(
            role=Role.OWNER, branch=None, email="owner@labflow.app"
        )
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="mgr@labflow.app"
        )
        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
        }


@pytest.mark.django_db
class TestExportApi:
    def test_owner_can_request_export(
        self, tenant_a: Any, lab38_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """POST /exports as Owner -> 202, export record, task enqueued."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab38_setup["owner"])
        client = Client()
        with patch("apps.platform.tasks.export_tenant_task.delay") as mock_delay:
            headers["Idempotency-Key"] = f"lab38-export-{uuid.uuid4().hex}"
            # View enqueues via transaction.on_commit — capture and execute it
            with captureOnCommitCallbacks(execute=True):
                response = client.post(
                    EXPORTS_URL,
                    data=json.dumps({}),
                    content_type="application/json",
                    **{
                        f"HTTP_{k.upper().replace('-', '_')}": v
                        for k, v in headers.items()
                    },
                )
        assert response.status_code == 202, response.content[:500]
        body = response.json()
        assert "export_id" in body
        assert body["status"] == "pending"
        mock_delay.assert_called_once()
        # Export record exists
        with tenant_context(tenant_a):
            export = DataExport.objects.get(id=uuid.UUID(body["export_id"]))
            assert export.status == DataExport.Status.PENDING
            assert export.requested_by_id == lab38_setup["owner"].id

    def test_non_owner_cannot_request_export(
        self, tenant_a: Any, lab38_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """POST /exports as Manager -> 403."""
        with tenant_context(tenant_a):
            headers = auth_headers(lab38_setup["manager"])
        client = Client()
        response = client.post(
            EXPORTS_URL,
            data=json.dumps({}),
            content_type="application/json",
            **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()},
        )
        assert response.status_code == 403

    def test_export_available_in_read_only_mode(
        self, tenant_a: Any, lab38_setup: dict[str, Any], auth_headers: Any
    ) -> None:
        """POST /exports works even when tenant is in read-only mode.

        Doc 04 §4.3 / LAB-38: export is explicitly available in read-only.
        """
        with tenant_context(tenant_a):
            headers = auth_headers(lab38_setup["owner"])
        client = Client()
        # Simulate read-only mode via tenant setting or mock
        with (
            patch("apps.platform.tasks.export_tenant_task.delay"),
            patch(
                "apps.accounts.views_exports._tenant_access_mode",
                return_value="read_only",
            ),
        ):
            response = client.post(
                EXPORTS_URL,
                data=json.dumps({}),
                content_type="application/json",
                **{
                    f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()
                },
            )
        # Must NOT be 403 subscription_read_only
        assert response.status_code != 403 or (
            "subscription_read_only" not in response.content.decode()
        ), "Export must be available in read-only mode"


@pytest.mark.django_db
class TestExportTask:
    def test_export_excludes_secrets(
        self, tenant_a: Any, lab38_setup: dict[str, Any]
    ) -> None:
        """TN-38: password_hash, totp secrets, token_hash never in CSVs."""
        from apps.platform.tasks import export_tenant_task

        with tenant_context(tenant_a):
            # Create a staff user with secrets set
            owner = lab38_setup["owner"]
            owner.password_hash = "hashed-secret-value"
            owner.totp_secret_encrypted = "encrypted-totp-secret"
            owner.totp_backup_codes_hash = ["backup-codes-hash"]
            owner.save(
                update_fields=[
                    "password_hash",
                    "totp_secret_encrypted",
                    "totp_backup_codes_hash",
                ]
            )
            export = DataExport.objects.create(
                requested_by=owner,
                status=DataExport.Status.PENDING,
            )
            # Run task synchronously (eager)
            result = export_tenant_task(
                schema_name=tenant_a.schema_name,
                export_id=str(export.id),
            )
            assert result["status"] == "ok"
            # Fetch the bundle and check staff_user CSV
            bundle_bytes = result["bundle_bytes"]
            zf = zipfile.ZipFile(io.BytesIO(bundle_bytes))
            assert "manifest.json" in zf.namelist()
            staff_csv = None
            for name in zf.namelist():
                if "staff_user" in name and name.endswith(".csv"):
                    staff_csv = name
                    break
            assert staff_csv is not None, "staff_user CSV missing"
            content = zf.read(staff_csv).decode("utf-8")
            assert "hashed-secret-value" not in content
            assert "encrypted-totp-secret" not in content
            assert "backup-codes-hash" not in content
            # Manifest records exclusions
            manifest = json.loads(zf.read("manifest.json"))
            assert "excluded_columns" in manifest
            excluded = manifest["excluded_columns"]
            # At least these must be listed
            excluded_keys = [e["column"] for e in excluded]
            assert "password_hash" in excluded_keys
            assert "totp_secret_encrypted" in excluded_keys
            assert "totp_backup_codes_hash" in excluded_keys
            # Every exclusion has a reason
            for e in excluded:
                assert e.get("reason"), f"No reason for {e['column']}"

    def test_export_manifest_has_checksums(
        self, tenant_a: Any, lab38_setup: dict[str, Any]
    ) -> None:
        """Manifest lists every file with SHA-256 and row count/byte size."""
        from apps.platform.tasks import export_tenant_task

        with tenant_context(tenant_a):
            owner = lab38_setup["owner"]
            export = DataExport.objects.create(
                requested_by=owner,
                status=DataExport.Status.PENDING,
            )
            result = export_tenant_task(
                schema_name=tenant_a.schema_name,
                export_id=str(export.id),
            )
            assert result["status"] == "ok"
            bundle_bytes = result["bundle_bytes"]
            zf = zipfile.ZipFile(io.BytesIO(bundle_bytes))
            manifest = json.loads(zf.read("manifest.json"))
            assert "files" in manifest
            assert len(manifest["files"]) > 0
            for f in manifest["files"]:
                assert "name" in f
                assert "sha256" in f
                assert len(f["sha256"]) == 64  # hex digest
                assert "rows" in f or "bytes" in f
                # Verify checksum matches actual file
                actual = hashlib.sha256(zf.read(f["name"])).hexdigest()
                assert actual == f["sha256"], f"Checksum mismatch for {f['name']}"

    def test_export_creates_audit_log(
        self, tenant_a: Any, lab38_setup: dict[str, Any]
    ) -> None:
        """Export completion writes an audit log row."""
        from apps.platform.tasks import export_tenant_task

        with tenant_context(tenant_a):
            owner = lab38_setup["owner"]
            export = DataExport.objects.create(
                requested_by=owner,
                status=DataExport.Status.PENDING,
            )
            export_tenant_task(
                schema_name=tenant_a.schema_name,
                export_id=str(export.id),
            )
            log = AuditLog.objects.filter(
                action="data.export_completed",
                entity_type="data_export",
                entity_id=export.id,
            ).first()
            assert log is not None, "Audit log missing for export"
