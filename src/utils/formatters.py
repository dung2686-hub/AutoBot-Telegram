import re

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
    }
    return icons.get(tx_type, "📋")
