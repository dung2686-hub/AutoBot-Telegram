import json
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.formatters import format_vnd, format_date, format_account_list
from src.utils.keyboards import back_to_menu_keyboard, pagination_keyboard

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 5


@error_handler
@ensure_user
async def history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show paginated order history."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    db_user = context.user_data["db_user"]

    # Parse page from callback data
    parts = query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0

    total = await db.count_user_orders(db_user["id"])
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    orders = await db.get_user_orders(
        db_user["id"],
        limit=ITEMS_PER_PAGE,
        offset=page * ITEMS_PER_PAGE,
    )

    if not orders:
        await query.edit_message_text(
            t("history_empty", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    text = t("history_title", lang)
    keyboard_rows = []

    for order in orders:
        text += t("history_item", lang,
            name=order["product_name"],
            qty=order["quantity"],
            price=format_vnd(order["total_amount"]),
            date=format_date(order["created_at"]),
        )
        keyboard_rows.append([
            InlineKeyboardButton(
                f"📋 #{order['id']} — {order['product_name']}",
                callback_data=f"history:detail:{order['id']}",
            )
        ])

    # Pagination
    page_buttons = pagination_keyboard("history", page, total_pages, lang)
    if page_buttons:
        keyboard_rows.append(page_buttons)

    keyboard_rows.append([
        InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")
    ])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
        parse_mode="HTML",
    )


@error_handler
@ensure_user
async def history_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detail of a specific order."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]

    parts = query.data.split(":")
    order_id = int(parts[2])

    order = await db.get_order_by_id(order_id)
    if not order:
        await query.edit_message_text(
            t("error_generic", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    delivered = json.loads(order.get("delivered_data", "[]"))
    accounts_text = format_account_list(delivered, lang)

    text = t("history_detail", lang,
        id=order["id"],
        name=order["product_name"],
        quantity=order["quantity"],
        price=format_vnd(order["total_amount"]),
        date=format_date(order["created_at"]),
        accounts=accounts_text,
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_back", lang), callback_data="menu:history")],
        [InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")],
    ])

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
