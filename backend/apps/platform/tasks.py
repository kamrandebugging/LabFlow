from typing import Any

from celery import shared_task


@shared_task(
    name="tenants.provision",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def provision_tenant_task(self: Any, tenant_slug: str) -> dict[str, Any]:
    """Execute the resumable provisioning state machine for a tenant (Doc 04 §5)."""
    from apps.platform.provisioning import run_provisioning_state_machine

    return run_provisioning_state_machine(tenant_slug=tenant_slug)


# ---------------------------------------------------------------------------
# tenants.export_tenant (KAN-163 / LAB-38, original LAB-49)
# ---------------------------------------------------------------------------

EXPORT_TASK_NAME = "tenants.export_tenant"

# Doc 04 §4.3: secret exclusion list — these columns are NEVER exported.
# The manifest records each exclusion with its reason.
SECRET_EXCLUSIONS: tuple[tuple[str, str], ...] = (
    ("password_hash", "staff_user credential hash — excluded for security"),
    (
        "totp_secret_encrypted",
        "staff_user TOTP secret — excluded for security",
    ),
    (
        "totp_backup_codes_hash",
        "staff_user TOTP backup codes — excluded for security",
    ),
    ("token_hash", "authentication/report token hash — excluded for security"),
)
SECRET_COLUMN_NAMES = frozenset(name for name, _ in SECRET_EXCLUSIONS)


def _is_secret_column(column_name: str) -> bool:
    """True if the column is on the §4.3 secret exclusion list.

    Matches exact names (password_hash, totp_secret_encrypted,
    totp_backup_codes_hash) and any column ending in token_hash (every
    token_hash column, per §4.3).
    """
    if column_name in SECRET_COLUMN_NAMES:
        return True
    return column_name == "token_hash" or column_name.endswith("_token_hash")


def _exclusion_reason(column_name: str) -> str:
    """Human-readable reason for the manifest's excluded_columns list."""
    for name, reason in SECRET_EXCLUSIONS:
        if column_name == name:
            return reason
    if column_name == "token_hash" or column_name.endswith("_token_hash"):
        return "token hash column — excluded for security"
    return "excluded for security"


@shared_task(name=EXPORT_TASK_NAME, queue="maintenance", max_retries=0)
def export_tenant_task(schema_name: str, export_id: str) -> dict[str, Any]:
    """Export a tenant's data for the Lab Owner (Doc 04 §4.3; KAN-163/LAB-38).

    Runs in the tenant context (schema_context). Produces:
    - one CSV per tenant table (full record, not a summary),
    - every report PDF at its stored pdf_key,
    - manifest.json naming every file with row count or byte size and
      SHA-256 checksum.

    Secrets are never exported (§4.3 exclusion list); the manifest records
    exactly which columns were excluded and why.

    The bundle is built on disk and streamed into storage; the API layer mints
    the 7-day signed link. Idempotent per export_id: a repeat run for a
    COMPLETE export returns the existing bundle key without re-exporting.
    """
    import logging
    import uuid
    from datetime import timedelta

    from django.conf import settings
    from django.core.files.storage import default_storage
    from django.db import transaction
    from django.utils import timezone
    from django_tenants.utils import schema_context

    logger = logging.getLogger(__name__)

    with schema_context(schema_name):
        from apps.accounts.models import AuditLog, DataExport

        try:
            export_pk = uuid.UUID(export_id)
        except (ValueError, TypeError):
            logger.warning("tenants.export_tenant: bad export id %r — skip", export_id)
            return {"status": "skipped", "reason": "bad_export_id"}

        with transaction.atomic():
            try:
                export = DataExport.objects.select_for_update().get(pk=export_pk)
            except DataExport.DoesNotExist:
                logger.warning(
                    "tenants.export_tenant: export %s not found in %s — skip",
                    export_id,
                    schema_name,
                )
                return {"status": "skipped", "reason": "export_not_found"}
            if export.status == DataExport.Status.COMPLETE:
                return {
                    "status": "ok",
                    "export_id": str(export.id),
                    "bundle_key": export.bundle_key,
                    "deduplicated": True,
                }
            export.status = DataExport.Status.RUNNING
            export.save(update_fields=["status", "updated_at"])

        # Build on disk (never whole-tenant list() + BytesIO) and stream the
        # finished ZIP into storage (LAB-49 Phase 2.5).
        import contextlib
        import os
        import tempfile

        from django.core.files import File

        temp_path = os.path.join(
            tempfile.gettempdir(), f"labflow-export-{export.id}.zip"
        )
        try:
            try:
                manifest = _build_export_bundle_to_path(schema_name, temp_path)
            except Exception as exc:
                logger.exception("tenants.export_tenant: export %s failed", export_id)
                with transaction.atomic():
                    locked = DataExport.objects.select_for_update().get(pk=export.pk)
                    locked.status = DataExport.Status.FAILED
                    locked.error = f"{type(exc).__name__}: {exc}"[:2000]
                    locked.save(update_fields=["status", "error", "updated_at"])
                raise

            # Persist bundle under tenant prefix; mint 7-day signed link.
            bundle_key = f"exports/{schema_name}/{export.id}/export.zip"
            if default_storage.exists(bundle_key):
                default_storage.delete(bundle_key)
            with open(temp_path, "rb") as bundle_file:
                default_storage.save(bundle_key, File(bundle_file))
            bundle_bytes = os.path.getsize(temp_path)
            # Eager-mode test seam only: production never loads the ZIP in RAM.
            eager_bundle = b""
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                with open(temp_path, "rb") as bundle_file:
                    eager_bundle = bundle_file.read()

            from django.core.signing import TimestampSigner

            signer = TimestampSigner(salt="labflow.data-export")
            signed = signer.sign(str(export.id))
            download_url = f"/api/v1/exports/{export.id}/download?sig={signed}"
            expires_at = timezone.now() + timedelta(days=7)

            with transaction.atomic():
                locked = DataExport.objects.select_for_update().get(pk=export.pk)
                locked.status = DataExport.Status.COMPLETE
                locked.bundle_key = bundle_key
                locked.download_url = download_url
                locked.download_expires_at = expires_at
                locked.completed_at = timezone.now()
                locked.error = None
                locked.save(
                    update_fields=[
                        "status",
                        "bundle_key",
                        "download_url",
                        "download_expires_at",
                        "completed_at",
                        "error",
                        "updated_at",
                    ]
                )
                AuditLog.objects.create(
                    actor_id=locked.requested_by_id,
                    action="data.export_completed",
                    entity_type="data_export",
                    entity_id=locked.id,
                    after_jsonb={
                        "export_id": str(locked.id),
                        "bundle_key": bundle_key,
                        "file_count": len(manifest["files"]),
                        "event": "data.export_completed",
                    },
                )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)

        logger.info(
            "tenants.export_tenant: export %s complete (%d files, %d bytes)",
            export_id,
            len(manifest["files"]),
            bundle_bytes,
        )
        result: dict[str, Any] = {
            "status": "ok",
            "export_id": str(export.id),
            "bundle_key": bundle_key,
            "bundle_size": bundle_bytes,
            "manifest": manifest,
        }
        if eager_bundle:
            result["bundle_bytes"] = eager_bundle
        return result


def _write_table_csv(
    zf: Any,
    arcname: str,
    field_names: list[str],
    queryset: Any,
) -> tuple[str, int, int]:
    """Stream one table into a ZIP entry; return (sha256, rows, bytes)."""
    import csv
    import hashlib
    import io

    hasher = hashlib.sha256()
    row_count = 0
    byte_count = 0
    with zf.open(arcname, "w") as raw:
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def flush_buffer() -> None:
            nonlocal byte_count
            data = buffer.getvalue().encode("utf-8")
            raw.write(data)
            hasher.update(data)
            byte_count += len(data)
            buffer.seek(0)
            buffer.truncate(0)

        writer.writerow(field_names)
        flush_buffer()
        for row in queryset.iterator(chunk_size=2000):
            writer.writerow(["" if value is None else str(value) for value in row])
            row_count += 1
            if buffer.tell() >= 1_000_000:
                flush_buffer()
        flush_buffer()
    return hasher.hexdigest(), row_count, byte_count


def _build_export_bundle_to_path(schema_name: str, path: str) -> dict[str, Any]:
    """Build the export ZIP on disk: CSVs + PDFs + manifest.json.

    Streams one table at a time and one PDF chunk at a time into the ZIP, so
    neither the whole tenant nor the whole bundle is held in memory (LAB-49
    Phase 2.5). Secrets excluded per §4.3. Returns the manifest dict.
    """
    import hashlib
    import json
    import zipfile

    from django.apps import apps as django_apps
    from django.core.files.storage import default_storage
    from django.db import connection
    from django.utils import timezone

    files: list[dict[str, Any]] = []
    excluded_columns: list[dict[str, str]] = []
    seen_exclusions: set[tuple[str, str]] = set()

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # One CSV per tenant table (all models in the tenant schema).
        for model in django_apps.get_models():
            table = model._meta.db_table
            # Skip non-tenant tables (Django internals, public-schema only).
            if table.startswith("django_") or table in ("spatial_ref_sys",):
                continue
            # Only tables that exist in this schema.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass(%s)",
                    [f'"{schema_name}"."{table}"'],
                )
                if cursor.fetchone()[0] is None:
                    continue

            field_names: list[str] = []
            for field in model._meta.local_fields:
                col = field.column or field.name
                if _is_secret_column(col):
                    key = (table, col)
                    if key not in seen_exclusions:
                        seen_exclusions.add(key)
                        excluded_columns.append(
                            {
                                "table": table,
                                "column": col,
                                "reason": _exclusion_reason(col),
                            }
                        )
                    continue
                field_names.append(field.name)

            queryset = (
                model.objects.values_list(*field_names).order_by("pk")  # type: ignore[attr-defined]
                if field_names
                else model.objects.none()  # type: ignore[attr-defined]
            )
            arcname = f"tables/{table}.csv"
            sha256, row_count, byte_count = _write_table_csv(
                zf, arcname, field_names, queryset
            )
            files.append(
                {
                    "name": arcname,
                    "sha256": sha256,
                    "rows": row_count,
                    "bytes": byte_count,
                }
            )

        # Every report PDF at its stored pdf_key, streamed in 1 MB chunks.
        try:
            from apps.reports.models import ReportVersion

            for version in ReportVersion.objects.all().order_by("report_id", "version"):
                pdf_key = version.pdf_key
                if not pdf_key or not default_storage.exists(pdf_key):
                    continue
                arcname = f"reports/{pdf_key}"
                hasher = hashlib.sha256()
                byte_count = 0
                with (
                    default_storage.open(pdf_key, "rb") as source,
                    zf.open(arcname, "w") as target,
                ):
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                        hasher.update(chunk)
                        byte_count += len(chunk)
                files.append(
                    {
                        "name": arcname,
                        "sha256": hasher.hexdigest(),
                        "bytes": byte_count,
                    }
                )
        except Exception:
            # Reports app may not have versions yet; not fatal.
            pass

        # Manifest (written last so it can list everything).
        manifest = {
            "exported_at": timezone.now().isoformat(),
            "schema": schema_name,
            "files": files,
            "excluded_columns": sorted(
                excluded_columns, key=lambda e: (e["table"], e["column"])
            ),
            "notes": (
                "Columns listed in excluded_columns were excluded for security "
                "per Doc 04 §4.3 (never exported); their absence is not data loss."
            ),
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        zf.writestr("manifest.json", manifest_bytes)

    return manifest
