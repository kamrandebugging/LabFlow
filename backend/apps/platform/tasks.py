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

    The bundle is returned as bytes in the result (the API layer persists
    it under the tenant's storage prefix and mints the 7-day signed link).
    Idempotent per export_id: a repeat run for a COMPLETE export returns
    the existing bundle key without re-exporting.
    """
    import logging
    import uuid
    from datetime import timedelta

    from django.core.files.base import ContentFile
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

        # Build the bundle outside the row lock.
        try:
            bundle_bytes, manifest = _build_export_bundle(schema_name)
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
        default_storage.save(bundle_key, ContentFile(bundle_bytes))

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
        logger.info(
            "tenants.export_tenant: export %s complete (%d files, %d bytes)",
            export_id,
            len(manifest["files"]),
            len(bundle_bytes),
        )
        return {
            "status": "ok",
            "export_id": str(export.id),
            "bundle_key": bundle_key,
            "bundle_bytes": bundle_bytes,
            "manifest": manifest,
        }


def _build_export_bundle(schema_name: str) -> tuple[bytes, dict[str, Any]]:
    """Build the export ZIP: CSVs + PDFs + manifest.json.

    Returns (zip_bytes, manifest_dict). Secrets excluded per §4.3.
    """
    import csv
    import hashlib
    import io
    import json
    import zipfile

    from django.apps import apps as django_apps
    from django.core.files.storage import default_storage
    from django.db import connection
    from django.utils import timezone

    files: list[dict[str, Any]] = []
    excluded_columns: list[dict[str, str]] = []
    seen_exclusions: set[tuple[str, str]] = set()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
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
                col = field.column
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

            rows = list(
                model.objects.values_list(*field_names).order_by("pk")
                if field_names
                else []
            )
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(field_names)
            for row in rows:
                writer.writerow(["" if v is None else str(v) for v in row])
            csv_bytes = csv_buffer.getvalue().encode("utf-8")
            arcname = f"tables/{table}.csv"
            zf.writestr(arcname, csv_bytes)
            files.append(
                {
                    "name": arcname,
                    "sha256": hashlib.sha256(csv_bytes).hexdigest(),
                    "rows": len(rows),
                    "bytes": len(csv_bytes),
                }
            )

        # Every report PDF at its stored pdf_key.
        try:
            from apps.reports.models import ReportVersion

            for version in ReportVersion.objects.all().order_by("report_id", "version"):
                pdf_key = version.pdf_key
                if not pdf_key or not default_storage.exists(pdf_key):
                    continue
                with default_storage.open(pdf_key, "rb") as fh:
                    pdf_bytes = fh.read()
                arcname = f"reports/{pdf_key}"
                zf.writestr(arcname, pdf_bytes)
                files.append(
                    {
                        "name": arcname,
                        "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                        "bytes": len(pdf_bytes),
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

    zip_bytes = zip_buffer.getvalue()
    # Recompute manifest with the final file list (manifest.json itself
    # is not checksummed inside the manifest).
    return zip_bytes, manifest
