"""Object-storage seam for report PDFs (KAN-155 / LAB-30, Doc 03 §5.6 RP-2).

Doc 01 specifies Cloudflare R2 / MinIO for object storage. This module wraps
Django's default storage backend behind a small, report-specific interface so
the R2/MinIO backend can be swapped in later via Django's STORAGES setting
without touching the generation task.

Current wiring:
- dev/test: local FileSystemStorage (Django default) — PDFs land under
  MEDIA_ROOT/reports/<report_id>/<version>.pdf.
- prod: point the "default" (or a dedicated) STORAGES entry at
  django-storages' S3Boto3Storage configured for R2/MinIO; no code change
  needed here.

The pdf_key itself is versioned (reports/{report_id}/{version}.pdf, RP-2) —
object-storage versioning is deliberately NOT relied on.
"""

from __future__ import annotations

from typing import Any, cast

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.signing import TimestampSigner
from django.urls import reverse

# Salt for the short-lived local download URLs (dev/test path below).
REPORT_FILE_SIGNER_SALT = "labflow.report-file"


class ReportStorage:
    """Thin wrapper around Django's default storage for report PDFs."""

    def save_pdf(self, pdf_key: str, data: bytes) -> None:
        """Persist PDF bytes at pdf_key, overwriting any existing object.

        Overwrite is intentional: retries upload to the same deterministic
        key (§10) — an orphaned object from a crashed attempt is replaced,
        never served (serving resolves through report_version.pdf_key rows).
        """
        if default_storage.exists(pdf_key):
            default_storage.delete(pdf_key)
        default_storage.save(pdf_key, ContentFile(data))

    def pdf_exists(self, pdf_key: str) -> bool:
        return default_storage.exists(pdf_key)

    def open_pdf(self, pdf_key: str) -> Any:
        return default_storage.open(pdf_key, "rb")

    def presigned_url(self, pdf_key: str, expires_seconds: int = 900) -> str:
        """Short-lived download URL for a report PDF (Doc 01 §14, RP-8).

        Two-layer token design (§9): the patient link (days) opens the door;
        this URL (minutes) serves the file.

        - Prod path: STORAGES "default" points at django-storages'
          S3Boto3Storage configured for R2/MinIO with querystring auth —
          `url(..., expire=...)` returns a real pre-signed URL (duck-typed
          on `bucket_name` so no import of django-storages is needed here).
        - Dev/test path: local FileSystemStorage cannot sign URLs, so the
          URL points at the signed local download route
          GET /api/v1/report-files/<sig>/, where <sig> is a TimestampSigner
          signature over the pdf_key valid for `expires_seconds`. The
          download view re-validates the signature AND the tenant-scoped
          report_version row before streaming.
        """
        backend = cast(Any, default_storage)
        if hasattr(backend, "bucket_name"):
            return str(
                backend.url(
                    pdf_key,
                    expire=expires_seconds,
                    parameters={"ResponseContentDisposition": "inline"},
                )
            )
        signed = TimestampSigner(salt=REPORT_FILE_SIGNER_SALT).sign(pdf_key)
        return reverse("report-file-download", kwargs={"signed": signed})
