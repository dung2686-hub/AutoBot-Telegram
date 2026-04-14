import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.formatters import format_vnd, format_date, esc
from src.utils.keyboards import back_to_menu_keyboard

logger = logging.getLogger(__name__)


@error_handler
@ensure_user
async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    db_user = context.user_data["db_user"]

    total_orders = await db.count_user_orders(db_user["id"])

    text = t("profile_title", lang,
        full_name=esc(db_user.get("full_name", "N/A")),
        username=db_user.get("username", "N/A"),
        balance=format_vnd(db_user["balance"]),
        total_orders=total_orders,
        joined=format_date(db_user.get("created_at", "")),
    )

    await query.edit_message_text(
        text,
        reply_markup=back_to_menu_keyboard(lang),
        parse_mode="HTML",
    )
