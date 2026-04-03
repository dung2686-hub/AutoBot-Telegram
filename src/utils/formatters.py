def format_vnd(amount: int) -> str:
    """Format integer to VND string: 100000 -> '100,000đ'"""
    return f"{amount:,}đ".replace(",", ".")


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
            lines.append(f"{icon} {label}: <code>{val}</code>")
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
    """Format ISO date to readable: '2026-04-02T14:00:00' -> '02/04/2026 14:00'"""
    if not date_str:
        return "N/A"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(date_str)[:16]


def tx_icon(tx_type: str) -> str:
    icons = {
        "deposit": "💳",
        "purchase": "🛒",
        "refund": "↩️",
        "admin_credit": "🔧",
    }
    return icons.get(tx_type, "📋")
