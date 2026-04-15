import io
import logging
import time

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.formatters import format_vnd, format_date, tx_icon, esc
from src.utils.keyboards import wallet_keyboard, back_to_menu_keyboard
from src.services.vietqr import generate_qr_image, get_bank_display_name

logger = logging.getLogger(__name__)

ENTER_AMOUNT = 1


# ── Wallet Menu ───────────────────────────────────────────

@error_handler
@ensure_user
async def wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show wallet with balance."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db_user = context.user_data["db_user"]

    text = t("wallet_title", lang, balance=format_vnd(db_user["balance"]))
    await query.edit_message_text(text, reply_markup=wallet_keyboard(lang), parse_mode="HTML")


# ── Deposit Flow (ConversationHandler) ────────────────────

@error_handler
@ensure_user
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start deposit flow — ask for amount."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    text = t("deposit_enter_amount", lang)

    await query.edit_message_text(text, parse_mode="HTML")
    context.user_data["active_conv"] = "deposit"
    return ENTER_AMOUNT


@error_handler
@ensure_user
async def deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("active_conv") != "deposit":
        return ConversationHandler.END

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    db_user = context.user_data["db_user"]

    raw = update.message.text.strip().replace(".", "").replace(",", "").replace("đ", "")

    try:
        amount = int(raw)
    except ValueError:
        await update.message.reply_text(t("deposit_invalid_amount", lang), parse_mode="HTML")
        return ENTER_AMOUNT

    if amount < 10000:
        await update.message.reply_text(t("deposit_invalid_amount", lang), parse_mode="HTML")
        return ENTER_AMOUNT

    # Save pending deposit first to get ID
    temp_code = f"PENDING_{int(time.time() * 1000)}"
    deposit = await db.create_deposit(
        user_id=db_user["id"],
        amount=amount,
        code=temp_code,
        expire_minutes=config.deposit_expire_minutes,
    )
    deposit_id = deposit["id"]
    code = f"NAP{deposit_id}"
    await db.conn.execute("UPDATE deposits SET code = ? WHERE id = ?", (code, deposit_id))
    await db.conn.commit()

    # Generate QR image with 3-tier fallback (URL → API → offline)
    qr_bytes = await generate_qr_image(amount, code)
    bank_display = get_bank_display_name(config.bank_bin)

    text = t("deposit_qr", lang,
        amount=format_vnd(amount),
        code=code,
        expire_min=config.deposit_expire_minutes,
        bank_name=bank_display,
        bank_account=config.bank_account,
        bank_account_name=config.bank_account_name,
    )

    await update.message.reply_photo(
        photo=qr_bytes,
        caption=text,
        parse_mode="HTML",
    )

    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


async def deposit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel deposit flow."""
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


# ── Transaction History ───────────────────────────────────

@error_handler
@ensure_user
async def transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent transactions."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    db_user = context.user_data["db_user"]

    txns = await db.get_user_transactions(db_user["id"], limit=10)

    if not txns:
        await query.edit_message_text(
            t("tx_empty", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    text = t("tx_history_title", lang)
    for tx in txns:
        icon = tx_icon(tx["type"])
        amount_str = format_vnd(abs(tx["amount"]))
        if tx["amount"] > 0:
            amount_str = f"+{amount_str}"
        else:
            amount_str = f"-{amount_str}"

        text += t("tx_item", lang,
            icon=icon,
            description=tx["description"] or tx["type"],
            amount=amount_str,
            date=format_date(tx["created_at"]),
        )

    await query.edit_message_text(
        text,
        reply_markup=back_to_menu_keyboard(lang),
        parse_mode="HTML",
    )


def get_deposit_conversation() -> ConversationHandler:
    """Build ConversationHandler for deposit flow."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(deposit_start, pattern=r"^wallet:deposit$"),
        ],
        states={
            ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_received),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(deposit_cancel, pattern=r"^menu:"),
        ],
        per_message=False,
        allow_reentry=True,
    )
