import io
import logging
import secrets
import string

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
from src.utils.formatters import format_vnd, format_date, tx_icon
from src.utils.keyboards import wallet_keyboard, back_to_menu_keyboard

logger = logging.getLogger(__name__)

ENTER_AMOUNT = 1


def _generate_payment_code(user_id: int) -> str:
    """Generate unique payment code: NAP + 8 random chars."""
    chars = string.ascii_uppercase + string.digits
    rand = "".join(secrets.choice(chars) for _ in range(8))
    return f"NAP{rand}"


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
    return ENTER_AMOUNT


@error_handler
@ensure_user
async def deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process entered deposit amount → generate QR."""
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
    import time
    temp_code = f"PENDING_{int(time.time() * 1000)}"
    deposit = await db.create_deposit(
        user_id=db_user["id"],
        amount=amount,
        code=temp_code,
        expire_minutes=config.deposit_expire_minutes,
    )
    deposit_id = deposit["id"]
    code = f"NAP {deposit_id}"
    await db.conn.execute("UPDATE deposits SET code = ? WHERE id = ?", (code, deposit_id))
    await db.conn.commit()

    # Generate QR URL (free, no API key needed)
    from urllib.parse import quote
    qr_url = (
        f"https://img.vietqr.io/image/{config.bank_bin}-{config.bank_account}-compact2.png"
        f"?amount={amount}&addInfo={quote(code)}&accountName={quote(config.bank_account_name)}"
    )

    # Map bank_bin to display name
    bank_names = {
        "mbb": "MBBank", "tcb": "Techcombank", "vcb": "Vietcombank",
        "acb": "ACB", "tpb": "TPBank", "bidv": "BIDV",
        "vtb": "VietinBank", "vpb": "VPBank", "scb": "Sacombank",
    }
    bank_display = bank_names.get(config.bank_bin.lower(), config.bank_bin.upper())

    text = t("deposit_qr", lang,
        amount=format_vnd(amount),
        code=code,
        expire_min=config.deposit_expire_minutes,
        bank_name=bank_display,
        bank_account=config.bank_account,
        bank_account_name=config.bank_account_name,
    )

    await update.message.reply_photo(
        photo=qr_url,
        caption=text,
        parse_mode="HTML",
    )

    return ConversationHandler.END


async def deposit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel deposit flow."""
    if update.callback_query:
        await update.callback_query.answer()
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
    )
