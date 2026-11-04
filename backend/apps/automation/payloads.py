"""Webhook payload envelope (Doc 06 §5.1, Doc 01 §13).

The envelope is fixed; only ``data`` varies per event (§6). The timestamp is
ISO 8601 UTC set when the payload is built — n8n rejects a webhook whose
timestamp is more than 5 minutes old (replay guard, §5.2 TS-1).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from django.utils import timezone


def utc_now_iso() -> str:
    """Current UTC time as ISO 8601 with trailing Z (e.g. 2026-10-20T08:15:30Z)."""
    return (
        timezone.now()
        .astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_timestamp(value: str) -> datetime:
    """Parse an envelope timestamp back to an aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_webhook_payload(
    *,
    event: str,
    tenant_slug: str,
    callback_url: str,
    idempotency_key: str,
    data: dict[str, Any],
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build the six-field webhook envelope (Doc 06 §5.1)."""
    return {
        "event": event,
        "tenant_slug": tenant_slug,
        "callback_url": callback_url,
        "idempotency_key": idempotency_key,
        "timestamp": timestamp if timestamp is not None else utc_now_iso(),
        "data": data,
    }


def serialize_payload(payload: dict[str, Any]) -> bytes:
    """Serialize to the exact bytes that are signed and sent.

    Deterministic (sorted keys, compact separators) so the signature covers
    stable bytes. Doc 06 F-1 / AU-33: any re-serialised body with different
    spacing fails verification, so both sides must use these exact bytes.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
