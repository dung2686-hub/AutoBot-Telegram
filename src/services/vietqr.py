import io
import logging
from typing import Optional
from urllib.parse import quote

import httpx
import qrcode

from src.config import config

logger = logging.getLogger(__name__)

# BIN code mapping — VietQR requires numeric BIN, not text aliases
BANK_BIN_MAP = {
    # Text alias → Numeric BIN
    "mbb": "970422", "mbbank": "970422",
    "tcb": "970407", "techcombank": "970407",
    "vcb": "970436", "vietcombank": "970436",
    "acb": "970416",
    "tpb": "970423", "tpbank": "970423",
    "bidv": "970418",
    "vtb": "970415", "vietinbank": "970415",
    "vpb": "970432", "vpbank": "970432",
    "scb": "970429", "sacombank": "970429",
    "msb": "970426",
    "shb": "970443",
    "ocb": "970448",
    "hdbank": "970437",
    "eximbank": "970431",
    "abbank": "970425",
    "baoViet": "970438",
    "pvcombank": "970412",
    "namabank": "970428",
    "lpb": "970449", "lienvietpostbank": "970449",
    "seabank": "970440",
    "vib": "970441",
    "dong_a": "970406",
}

# Display name mapping
BANK_DISPLAY_NAMES = {
    "970422": "MBBank",
    "970407": "Techcombank",
    "970436": "Vietcombank",
    "970416": "ACB",
    "970423": "TPBank",
    "970418": "BIDV",
    "970415": "VietinBank",
    "970432": "VPBank",
    "970429": "Sacombank",
    "970426": "MSB",
    "970443": "SHB",
    "970448": "OCB",
    "970437": "HDBank",
    "970431": "Eximbank",
    "970425": "ABBank",
    "970438": "BaoViet Bank",
    "970412": "PVcomBank",
    "970428": "NamABank",
    "970449": "LienVietPostBank",
    "970440": "SeABank",
    "970441": "VIB",
    "970406": "DongA Bank",
}


def resolve_bank_bin(raw_bin: str) -> str:
    """Convert text alias to numeric BIN. Pass through if already numeric."""
    if not raw_bin:
        return ""
    cleaned = raw_bin.strip().lower()
    return BANK_BIN_MAP.get(cleaned, raw_bin.strip())


def get_bank_display_name(raw_bin: str) -> str:
    """Get human-readable bank name from BIN or alias."""
    numeric = resolve_bank_bin(raw_bin)
    return BANK_DISPLAY_NAMES.get(numeric, raw_bin.upper())


def build_qr_url(amount: int, add_info: str) -> str:
    """Build VietQR image URL with proper BIN code."""
    bin_code = resolve_bank_bin(config.bank_bin)
    acc_no = config.bank_account
    acc_name = config.bank_account_name

    if not bin_code or not acc_no:
        raise ValueError("BANK_BIN or BANK_ACCOUNT not configured")

    return (
        f"https://img.vietqr.io/image/{bin_code}-{acc_no}-compact2.png"
        f"?amount={amount}&addInfo={quote(add_info)}&accountName={quote(acc_name)}"
    )


async def generate_qr_image(amount: int, payment_code: str) -> bytes:
    """Generate QR image bytes. Tries VietQR URL first, falls back to offline."""

    # Try fetching from VietQR URL
    try:
        qr_url = build_qr_url(amount, payment_code)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(qr_url)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                logger.info("QR fetched from VietQR URL: %s", payment_code)
                return resp.content
            logger.warning("VietQR URL returned %d, falling back to offline", resp.status_code)
    except Exception as e:
        logger.warning("VietQR URL fetch failed, falling back to offline: %s", e)

    # Try online API (if keys configured)
    if config.vietqr_client_id and config.vietqr_api_key:
        try:
            return await _generate_online(amount, payment_code)
        except Exception as e:
            logger.warning("VietQR API failed, falling back to offline: %s", e)

    # Final fallback: generate QR locally
    return _generate_offline(amount, payment_code)


async def _generate_online(amount: int, payment_code: str) -> bytes:
    """Generate QR via VietQR.io API."""
    bin_code = resolve_bank_bin(config.bank_bin)

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
                "acqId": bin_code,
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
            if qr_data_url.startswith("data:image"):
                import base64
                _, encoded = qr_data_url.split(",", 1)
                return base64.b64decode(encoded)

            img_resp = await client.get(qr_data_url)
            return img_resp.content

        qr_string = data.get("data", {}).get("qrCode", "")
        if qr_string:
            return _make_qr_image(qr_string)

    raise ValueError("No QR data returned from VietQR API")


def _generate_offline(amount: int, payment_code: str) -> bytes:
    """Generate a simple QR code with bank transfer info."""
    bin_code = resolve_bank_bin(config.bank_bin)
    bank_name = get_bank_display_name(config.bank_bin)
    transfer_info = (
        f"Bank: {bank_name} ({bin_code})\n"
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
