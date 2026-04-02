import io
import logging
from typing import Optional

import httpx
import qrcode

from src.config import config

logger = logging.getLogger(__name__)


async def generate_vietqr(amount: int, payment_code: str) -> Optional[bytes]:
    """Generate VietQR image bytes via VietQR.io API or fallback to offline."""

    # Try online API first
    if config.vietqr_client_id and config.vietqr_api_key:
        try:
            return await _generate_online(amount, payment_code)
        except Exception as e:
            logger.warning("VietQR online failed, falling back to offline: %s", e)

    # Fallback: generate QR with bank info text
    return _generate_offline(amount, payment_code)


async def _generate_online(amount: int, payment_code: str) -> bytes:
    """Generate QR via VietQR.io API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.vietqr.io/v2/generate",
            headers={
                "x-client-id": config.vietqr_client_id,
                "x-api-key": config.vietqr_api_key,
                "Content-Type": "application/json",
            },
            json={
                "accountNo": config.bank_account,
                "accountName": config.bank_account_name,
                "acqId": config.bank_bin,
                "amount": str(amount),
                "addInfo": payment_code,
                "format": "text",
                "template": "compact2",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        qr_data_url = data.get("data", {}).get("qrDataURL", "")
        if qr_data_url:
            # qrDataURL is a base64 data URI → download as bytes
            if qr_data_url.startswith("data:image"):
                import base64
                _, encoded = qr_data_url.split(",", 1)
                return base64.b64decode(encoded)

            # If it's a URL, fetch it
            img_resp = await client.get(qr_data_url)
            return img_resp.content

        # Fallback: use qrCode string to generate locally
        qr_string = data.get("data", {}).get("qrCode", "")
        if qr_string:
            return _make_qr_image(qr_string)

    raise ValueError("No QR data returned from VietQR API")


def _generate_offline(amount: int, payment_code: str) -> bytes:
    """Generate a simple QR code with bank transfer info."""
    transfer_info = (
        f"Bank: {config.bank_bin}\n"
        f"Account: {config.bank_account}\n"
        f"Name: {config.bank_account_name}\n"
        f"Amount: {amount}\n"
        f"Note: {payment_code}"
    )
    return _make_qr_image(transfer_info)


def _make_qr_image(data: str) -> bytes:
    """Create QR code image bytes from string data."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
