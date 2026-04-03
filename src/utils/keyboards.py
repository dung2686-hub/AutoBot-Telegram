from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.i18n import t


def main_menu_keyboard(lang: str = "vi", admin: bool = False) -> InlineKeyboardMarkup:
    """Creates the main menu keyboard."""
    
    # Matching Bot B style
    k = [
        [InlineKeyboardButton("🛍️ Mua hàng", callback_data="menu:shop")],
        [
            InlineKeyboardButton("👤 Hồ sơ", callback_data="menu:profile"),
            InlineKeyboardButton("🕒 Lịch sử mua", callback_data="menu:history"),
        ],
        [InlineKeyboardButton("💳 Ví", callback_data="menu:wallet")],
        [InlineKeyboardButton("🎧 Hỗ trợ / Support", callback_data="menu:support")],
        [
            InlineKeyboardButton("🔗 Liên kết API", callback_data="menu:api"),
            InlineKeyboardButton("🌐 Ngôn ngữ", callback_data="menu:language")
        ],
    ]
    return InlineKeyboardMarkup(k)

def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="lang:vi")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang:en")],
        [InlineKeyboardButton("🔙 Quay lại / Back", callback_data="menu:main")],
    ])


def back_to_menu_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")],
    ])


def wallet_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_deposit", lang), callback_data="wallet:deposit")],
        [InlineKeyboardButton(t("btn_tx_history", lang), callback_data="wallet:transactions")],
        [InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")],
    ])


def confirm_cancel_keyboard(confirm_data: str, lang: str = "vi") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("btn_confirm", lang), callback_data=confirm_data),
            InlineKeyboardButton(t("btn_cancel", lang), callback_data="menu:main"),
        ],
    ])


def payment_options_keyboard(product_id: str, quantity: int, lang: str = "vi") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Thanh toán qua ví", callback_data=f"shop:execute:{product_id}:{quantity}")],
        [InlineKeyboardButton("💳 Thanh toán ngay", callback_data=f"shop:qr_pay:{product_id}:{quantity}")],
        [InlineKeyboardButton(t("btn_cancel", lang), callback_data="menu:main")],
    ])


def product_detail_keyboard(product_id: str, quantity: int, lang: str = "vi", max_qty: int = None) -> InlineKeyboardMarkup:
    next_qty = quantity + 1
    if max_qty is not None and next_qty > max_qty:
        next_qty = quantity  # Stay at current (➕ does nothing)

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("btn_quantity_down", lang), callback_data=f"shop:qty:{product_id}:{max(1, quantity - 1)}"),
            InlineKeyboardButton(f"  {quantity}  ", callback_data="noop"),
            InlineKeyboardButton(t("btn_quantity_up", lang), callback_data=f"shop:qty:{product_id}:{next_qty}"),
        ],
        [InlineKeyboardButton(t("btn_buy", lang), callback_data=f"shop:buy:{product_id}:{quantity}")],
        [InlineKeyboardButton(t("btn_back", lang), callback_data="menu:shop")],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="lang:vi")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang:en")],
        [InlineKeyboardButton("⬅️", callback_data="menu:main")],
    ])


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast")],
        [InlineKeyboardButton("💰 Markup Settings", callback_data="admin:markup")],
        [InlineKeyboardButton("💳 Manual Credit", callback_data="admin:credit")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin:refresh")],
    ])


def pagination_keyboard(prefix: str, page: int, total_pages: int, lang: str = "vi") -> list[InlineKeyboardButton]:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(t("btn_prev_page", lang), callback_data=f"{prefix}:page:{page - 1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(t("btn_next_page", lang), callback_data=f"{prefix}:page:{page + 1}"))
    return buttons
