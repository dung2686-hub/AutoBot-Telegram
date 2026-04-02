from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.i18n import t


def main_menu_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_shop", lang), callback_data="menu:shop")],
        [
            InlineKeyboardButton(t("btn_profile", lang), callback_data="menu:profile"),
            InlineKeyboardButton(t("btn_history", lang), callback_data="menu:history"),
        ],
        [InlineKeyboardButton(t("btn_wallet", lang), callback_data="menu:wallet")],
        [InlineKeyboardButton(t("btn_support", lang), callback_data="menu:support")],
        [InlineKeyboardButton(t("btn_language", lang), callback_data="menu:language")],
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


def product_detail_keyboard(product_id: str, quantity: int, lang: str = "vi") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("btn_quantity_down", lang), callback_data=f"shop:qty:{product_id}:{max(1, quantity - 1)}"),
            InlineKeyboardButton(f"  {quantity}  ", callback_data="noop"),
            InlineKeyboardButton(t("btn_quantity_up", lang), callback_data=f"shop:qty:{product_id}:{quantity + 1}"),
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
