import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, admin_only, error_handler
from src.utils.formatters import format_vnd
from src.utils.keyboards import admin_keyboard, back_to_menu_keyboard

logger = logging.getLogger(__name__)

BROADCAST_MESSAGE = 10
CREDIT_INPUT = 11
MARKUP_INPUT = 12


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


# ── Broadcast ─────────────────────────────────────────────

@error_handler
@ensure_user
@admin_only
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(t("admin_broadcast_prompt", "vi"), parse_mode="HTML")
    return BROADCAST_MESSAGE


@error_handler
@ensure_user
@admin_only
async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    message_text = update.message.text

    user_ids = await db.get_all_user_ids()
    sent = 0

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message_text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass

    await update.message.reply_text(
        t("admin_broadcast_done", "vi", count=sent),
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ── Manual Credit ─────────────────────────────────────────

@error_handler
@ensure_user
@admin_only
async def credit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(t("admin_credit_prompt", "vi"), parse_mode="HTML")
    return CREDIT_INPUT


@error_handler
@ensure_user
@admin_only
async def credit_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]

    try:
        parts = update.message.text.strip().split()
        user_id = int(parts[0])
        amount = int(parts[1])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Format: <code>telegram_id amount</code>", parse_mode="HTML")
        return CREDIT_INPUT

    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text(f"❌ User {user_id} not found.")
        return CREDIT_INPUT

    new_balance = await db.update_balance(user_id, amount)

    await db.add_transaction(
        user_id=user["id"],
        tx_type="admin_credit",
        amount=amount,
        balance_after=new_balance,
        description=f"Admin credit",
    )

    await update.message.reply_text(
        t("admin_credit_done", "vi",
            amount=format_vnd(amount),
            user_id=user_id,
            balance=format_vnd(new_balance),
        ),
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    # Notify user
    try:
        from src.i18n import t as translate
        user_lang = user.get("language", "vi")
        await context.bot.send_message(
            chat_id=user_id,
            text=translate("deposit_success", user_lang,
                amount=format_vnd(amount),
                balance=format_vnd(new_balance),
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    return ConversationHandler.END


# ── Markup Settings ───────────────────────────────────────

@error_handler
@ensure_user
@admin_only
async def markup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    products = await canboso.get_products()
    markups = await db.get_all_markups()
    markup_map = {m["product_id"]: m["markup_percent"] for m in markups}

    text = "💰 <b>Markup Settings</b>\n\n"
    text += f"Default: {config.default_markup_percent}%\n\n"

    for p in products:
        pid = p.get("productId", "")
        name = p.get("name", "")
        current = markup_map.get(pid, config.default_markup_percent)
        original = format_vnd(p.get("price", 0))
        sell = format_vnd(int(p.get("price", 0) * (1 + current / 100)))
        text += f"• <b>{name}</b>\n  Gốc: {original} → Bán: {sell} ({current}%)\n\n"

    text += "\n📝 Để thay đổi, gửi:\n<code>product_id markup_percent</code>"

    await query.edit_message_text(text, reply_markup=admin_keyboard(), parse_mode="HTML")
    return MARKUP_INPUT


@error_handler
@ensure_user
@admin_only
async def markup_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    try:
        parts = update.message.text.strip().split()
        product_id = parts[0]
        markup = int(parts[1])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Format: <code>product_id markup_percent</code>", parse_mode="HTML")
        return MARKUP_INPUT

    product = canboso.find_product(product_id)
    name = product.get("name", product_id) if product else product_id

    await db.set_markup(product_id, name, markup)
    await update.message.reply_text(
        f"✅ Markup for <b>{name}</b> set to {markup}%",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    return ConversationHandler.END


def get_admin_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broadcast_start, pattern=r"^admin:broadcast$"),
            CallbackQueryHandler(credit_start, pattern=r"^admin:credit$"),
            CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
        ],
        states={
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send),
            ],
            CREDIT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, credit_execute),
            ],
            MARKUP_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, markup_set),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(admin_cancel, pattern=r"^(menu:|admin:refresh)"),
        ],
        per_message=False,
    )
