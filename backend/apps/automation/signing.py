"""HMAC-SHA256 webhook signing (Doc 06 §5.1, Doc 01 §13).

Django signs the raw request body with N8N_WEBHOOK_SECRET; the hex digest
travels in the X-LabFlow-Signature header. Both sides sign and verify the
exact bytes sent — a re-serialised body with different spacing fails
verification (Doc 06 F-1, AU-33).

The secret itself is never logged; only the digest (which is not reversible)
may appear in logs.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "X-LabFlow-Signature"


def sign_payload(raw_body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest of raw_body keyed with secret.

    Args:
        raw_body: The exact bytes that will be sent on the wire.
        secret: The shared N8N_WEBHOOK_SECRET (never logged by callers).
    """
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Constant-time check of a presented signature.

    Used by tests and by any Django-side verification of n8n-originated
    signed bodies. Malformed signatures are rejected, never raise.
    """
    try:
        expected = sign_payload(raw_body, secret)
    except Exception:
        return False
    return hmac.compare_digest(expected, signature)
