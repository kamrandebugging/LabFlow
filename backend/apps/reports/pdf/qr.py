"""
LAB-29 (KAN-154): QR verification payload (§9.3).

The QR encodes the report's patient access URL — the same
/api/v1/report-access/{token} link that delivery sends. One mechanism,
not two. Generated server-side as PNG, embedded as a local data URI
(no external images per §9.5).
"""

from __future__ import annotations

import base64
import io

import qrcode  # type: ignore[import-untyped]
from qrcode.image.pil import PilImage  # type: ignore[import-untyped]


def qr_payload_for_report(token: str) -> str:
    """The patient access URL encoded in the verification QR (§9.3)."""
    return f"/api/v1/report-access/{token}"


def make_qr_data_uri(payload: str) -> str:
    """Render the payload as a PNG QR code, returned as a data URI."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
