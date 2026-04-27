import html
import re


def esc(text: str) -> str:
    """Escape user-supplied text for Telegram HTML parse mode."""
    return html.escape(str(text)) if text else ""

def format_vnd(amount: int) -> str:
    """Format integer to VND string: 100000 -> '100,000đ'"""
    return f"{amount:,}đ".replace(",", ".")


def shorten_product_name(name: str) -> str:
    """Shorten common product keywords for mobile display. 
    E.g. Bao hanh full -> BHF, Bảo hành -> BH"""
    if not name:
        return name
        
    name = re.sub(r"(?i)\bbảo hành full\b|\bbao hanh full\b", "BHF", name)
    name = re.sub(r"(?i)\bbảo hành\b|\bbao hanh\b", "BH", name)
    name = re.sub(r"(?i)\b tháng\b|\b thang\b", "T", name)
    name = re.sub(r"(?i)\b năm\b|\b nam\b", "N", name)
    
    # Remove extra spaces caused by abbreviation if any
    name = re.sub(r"\s+", " ", name).strip()
    return name


def format_account_list(accounts: list[dict], lang: str = "vi") -> str:
    """Format delivered accounts for display — shows ALL fields dynamically."""
    if not accounts:
        return "N/A"

    field_icons = {
        "user": "📧", "email": "📧", "username": "👤",
        "password": "🔑", "pass": "🔑",
        "verifyEmail": "📬", "verify_email": "📬",
        "token": "🎫", "key": "🔐", "link": "🔗",
        "code": "📋", "pin": "📌",
    }

    lines = []
    copy_parts = []
    for i, acc in enumerate(accounts):
        if len(accounts) > 1:
            lines.append(f"━━ Tài khoản {i+1} ━━")
        acc_values = []
        for key, val in acc.items():
            if key.startswith("_") or not val:
                continue
            icon = field_icons.get(key, "📋")
            label = key.replace("_", " ").title()
            # Auto-convert ISO date fields to VN time
            display_val = val
            if isinstance(val, str) and ("T" in val and ("Z" in val or "+" in val)) or key.lower().endswith(("at", "date", "time")):
                try:
                    display_val = format_date(val)
                except Exception:
                    pass
            lines.append(f"{icon} {label}: <code>{display_val}</code>")
            if key.lower() in ("user", "email", "username", "password", "pass"):
                acc_values.append(str(val))
        if acc_values:
            copy_parts.append(" | ".join(acc_values))
        if len(accounts) > 1:
            lines.append("")

    # Quick copy block — tap once to copy all
    if copy_parts:
        lines.append("")
        copy_label = "📋 Copy nhanh:" if lang == "vi" else "📋 Quick copy:"
        lines.append(f"<b>{copy_label}</b>")
        lines.append(f"<code>{chr(10).join(copy_parts)}</code>")

    return "\n".join(lines)


def format_account_delivery(
    accounts: list[dict],
    lang: str = "vi",
    system_message: str = "",
) -> str:
    """Format normal account delivery with the legacy customer wrapper."""
    accounts_text = format_account_list(accounts, lang)
    title = "🔐 <b>YOUR ACCOUNT:</b>" if lang == "en" else "🔐 <b>TÀI KHOẢN CỦA BẠN:</b>"
    divider = "━━━━━━━━━━━━━━━━━━"
    wrapped = f"{title}\n{divider}\n{accounts_text}\n{divider}"

    if system_message and system_message != "Mua hàng thành công":
        label = "System notice" if lang == "en" else "Thông báo từ hệ thống"
        wrapped += f"\n\n📝 <b>{label}:</b>\n{esc(system_message)}"

    return wrapped


def build_slot_delivery_instruction(
    product_name: str,
    order_code: str,
    customer_email: str,
    lang: str = "vi",
) -> str:
    """Build Slot delivery instructions and include the customer's email."""
    is_openai = "chatgpt" in product_name.lower()
    platform = "OpenAI" if is_openai else "nhà cung cấp"
    safe_order_code = esc(order_code)
    safe_email = esc(customer_email or "bạn")

    if lang == "en":
        platform = "OpenAI" if is_openai else "the provider"
        safe_email = esc(customer_email or "you")
        return (
            f"Payment received for order {safe_order_code}. "
            f"<b>{safe_email}</b> has been invited to the workspace.\n\n"
            "⚠️ <b>Note:</b> Do not add another email to the workspace. "
            "If a violation is detected, the invited user and inviter may be removed without refund.\n\n"
            "<b>How to receive your slot:</b>\n"
            "1) Check your email inbox.\n"
            f"2) Find the email from {platform}.\n"
            '3) Click "Join workspace".\n'
            "4) Sign in to access the workspace."
        )

    return (
        f"Đã nhận thanh toán cho đơn {safe_order_code}. "
        f"Đã mời <b>{safe_email}</b> vào workspace.\n\n"
        "⚠️ <b>Lưu ý:</b> Không được thêm email khác vào workspace. Nếu phát hiện vi phạm, "
        "hệ thống sẽ kick người được mời thêm và kick người mời, đồng thời không hoàn tiền.\n\n"
        "<b>Hướng dẫn nhận slot:</b>\n"
        "1) Khách hàng kiểm tra email.\n"
        f"2) Tìm email từ {platform}.\n"
        '3) Nhấn "Join workspace".\n'
        "4) Đăng nhập để vào workspace."
    )


def format_slot_delivery(
    product_name: str,
    order_code: str,
    customer_email: str,
    lang: str = "vi",
) -> tuple[str, str]:
    """Return display text and persisted instruction payload for Slot orders."""
    instruction = build_slot_delivery_instruction(product_name, order_code, customer_email, lang)
    title = "📝 <b>Info & Instructions:</b>" if lang == "en" else "📝 <b>Thông tin & Hướng dẫn:</b>"
    return f"{title}\n{instruction}", instruction


def format_date(date_str: str) -> str:
    """Format ISO date to readable VN time: UTC -> GMT+7."""
    if not date_str:
        return "N/A"
    try:
        from datetime import datetime, timedelta, timezone
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        vn_tz = timezone(timedelta(hours=7))
        dt_vn = dt.astimezone(vn_tz)
        return dt_vn.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(date_str)[:16]


def now_vn():
    """Get current Vietnam time (GMT+7)."""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=7)))


def tx_icon(tx_type: str) -> str:
    icons = {
        "deposit": "💳",
        "purchase": "🛒",
        "refund": "↩️",
        "admin_credit": "🔧",
        "admin_debit": "➖",
        "referral_bonus": "🎁",
    }
    return icons.get(tx_type, "📋")
