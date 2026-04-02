def format_vnd(amount: int) -> str:
    """Format integer to VND string: 100000 -> '100,000đ'"""
    return f"{amount:,}đ".replace(",", ".")


def format_account_list(accounts: list[dict], lang: str = "vi") -> str:
    """Format delivered accounts for display."""
    from src.i18n import t

    if not accounts:
        return "N/A"

    lines = []
    for acc in accounts:
        lines.append(t("account_info", lang,
            user=acc.get("user", "N/A"),
            password=acc.get("password", "N/A"),
            verify_email=acc.get("verifyEmail", "N/A"),
        ))
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
