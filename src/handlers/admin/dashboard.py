import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.i18n import t
from src.utils.decorators import ensure_user, admin_only, error_handler
from src.utils.formatters import format_vnd
from src.utils.keyboards import admin_keyboard

logger = logging.getLogger(__name__)

@error_handler
@ensure_user
@admin_only
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin dashboard via /admin command."""
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    users_count = await db.count_users()
    today_orders = await db.get_today_orders_count()
    revenue = await db.get_total_revenue()
    canboso_data = await canboso.get_balance()
    canboso_balance = canboso_data.get("balance", 0)

    text = t("admin_title", "vi",
        users=users_count,
        today_orders=today_orders,
        revenue=format_vnd(revenue),
        canboso_balance=format_vnd(int(canboso_balance)),
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=admin_keyboard(), parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=admin_keyboard(), parse_mode="HTML")

@error_handler
@ensure_user
@admin_only
async def admin_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh admin dashboard."""
    await admin_command(update, context)
