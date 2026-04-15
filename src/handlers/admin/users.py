import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.i18n import t
from src.utils.decorators import ensure_user, admin_only, error_handler
from src.utils.formatters import format_vnd, format_date, esc
from src.utils.keyboards import admin_keyboard
from .states import CHECKUSER_INPUT, QUICKCREDIT_INPUT, CREDIT_INPUT

logger = logging.getLogger(__name__)

async def _lookup_user(update: Update, db, target_id: int) -> bool:
    """Shared lookup logic for checkuser. Returns True if user found."""
    user = await db.get_user(target_id)
    if not user:
        await update.message.reply_text(
            f"❌ Không tìm thấy user với Telegram ID <code>{target_id}</code>.",
            parse_mode="HTML",
        )
        return False

    username = user.get("username", "") or "N/A"
    full_name = esc(user.get("full_name", "") or "N/A")
    balance = user.get("balance", 0)
    lang = user.get("language", "vi")
    created = format_date(user.get("created_at", ""))
    referred_by = user.get("referred_by", None)

    text = (
        f"👤 <b>THÔNG TIN USER</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Telegram ID: <code>{target_id}</code>\n"
        f"📛 Tên: <b>{full_name}</b>\n"
        f"🔗 Username: @{username}\n"
        f"💰 Số dư ví: <b>{format_vnd(balance)}</b>\n"
        f"🌐 Ngôn ngữ: {lang}\n"
        f"📅 Tham gia: {created}\n"
    )
    if referred_by:
        text += f"🤝 Giới thiệu bởi: user_id #{referred_by}\n"

    txns = await db.get_user_transactions(user["id"], limit=5)
    if txns:
        text += "\n📜 <b>5 giao dịch gần nhất:</b>\n"
        for tx in txns:
            tx_amount = tx["amount"]
            sign = "+" if tx_amount > 0 else ""
            text += f"  • {tx['type']}: {sign}{format_vnd(tx_amount)} | {esc(tx.get('description', ''))} | {format_date(tx.get('created_at', ''))}\n"

    deposits = await db.get_user_deposits(user["id"], limit=5)
    if deposits:
        text += "\n💳 <b>5 lệnh nạp gần nhất:</b>\n"
        for d in deposits:
            status_icon = {"completed": "✅", "pending": "⏳", "expired": "⏱", "failed": "❌"}.get(d["status"], "❓")
            text += f"  • NAP{d['id']} | {format_vnd(d['amount'])} | {status_icon} {d['status']} | {format_date(d.get('created_at', ''))}\n"

    orders = await db.get_user_orders(user["id"], limit=5)
    if orders:
        text += "\n🛒 <b>5 đơn hàng gần nhất:</b>\n"
        for o in orders:
            status_icon = {"completed": "✅", "pending": "⏳", "expired": "⏱", "failed": "❌"}.get(o["status"], "❓")
            text += f"  • MUA{o['id']} | {esc(o.get('product_name', 'N/A'))} | {format_vnd(o['total_amount'])} | {status_icon} {o['status']}\n"

    keyboard = [
        [
            InlineKeyboardButton("💳 Cộng tiền", callback_data=f"admin:quickcredit:{target_id}"),
            InlineKeyboardButton("➖ Trừ tiền", callback_data=f"admin:quickdebit:{target_id}"),
        ],
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin:refresh")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return True

@error_handler
@ensure_user
@admin_only
async def checkuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Telegram ID phải là số.", parse_mode="HTML")
            return ConversationHandler.END
        db = context.bot_data["db"]
        await _lookup_user(update, db, target_id)
        return ConversationHandler.END

    await update.message.reply_text(
        "🔍 <b>Kiểm tra thông tin user</b>\n\n"
        "Gửi <b>Telegram ID</b> của user cần kiểm tra:",
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_checkuser"
    return CHECKUSER_INPUT

@error_handler
@ensure_user
@admin_only
async def checkuser_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("active_conv") != "admin_checkuser":
        return ConversationHandler.END

    raw = update.message.text.strip()
    try:
        target_id = int(raw)
    except ValueError:
        await update.message.reply_text("❌ Telegram ID phải là số. Thử lại:", parse_mode="HTML")
        return CHECKUSER_INPUT

    db = context.bot_data["db"]
    await _lookup_user(update, db, target_id)
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END

@error_handler
@ensure_user
@admin_only
async def quickcredit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    target_id = int(parts[2])
    is_debit = "quickdebit" in query.data

    context.user_data["quickcredit_target"] = target_id
    context.user_data["quickcredit_debit"] = is_debit

    action = "trừ" if is_debit else "cộng"
    emoji = "➖" if is_debit else "💳"

    db = context.bot_data["db"]
    user = await db.get_user(target_id)
    name = esc(user.get("full_name", "N/A") if user else "N/A")
    balance = user.get("balance", 0) if user else 0

    keyboard = [[InlineKeyboardButton("❌ Hủy", callback_data="admin:refresh")]]
    await query.edit_message_text(
        f"{emoji} <b>{action.upper()} tiền cho user</b>\n\n"
        f"👤 {name} (<code>{target_id}</code>)\n"
        f"💰 Số dư hiện tại: <b>{format_vnd(balance)}</b>\n\n"
        f"Nhập số tiền muốn <b>{action}</b>:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_quickcredit"
    return QUICKCREDIT_INPUT

@error_handler
@ensure_user
@admin_only
async def quickcredit_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("active_conv") != "admin_quickcredit":
        return ConversationHandler.END

    target_id = context.user_data.get("quickcredit_target")
    is_debit = context.user_data.get("quickcredit_debit", False)
    if not target_id:
        return ConversationHandler.END

    raw = update.message.text.strip().replace(".", "").replace(",", "").replace("đ", "")
    try:
        amount = int(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Số tiền không hợp lệ. Nhập số dương:", parse_mode="HTML")
        return QUICKCREDIT_INPUT

    db = context.bot_data["db"]
    user = await db.get_user(target_id)
    if not user:
        await update.message.reply_text("❌ User không tồn tại.")
        return ConversationHandler.END

    actual_amount = -amount if is_debit else amount
    action = "trừ" if is_debit else "cộng"
    new_balance = await db.update_balance(target_id, actual_amount)

    tx_type = "admin_debit" if is_debit else "admin_credit"
    await db.add_transaction(
        user_id=user["id"], tx_type=tx_type, amount=actual_amount,
        balance_after=new_balance, description=f"Admin {action} tiền",
    )

    emoji = "➖" if is_debit else "✅"
    await update.message.reply_text(
        f"{emoji} Đã <b>{action}</b> <b>{format_vnd(amount)}</b> cho user <code>{target_id}</code>\n"
        f"💰 Số dư mới: <b>{format_vnd(new_balance)}</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )

    try:
        if is_debit:
            msg = f"➖ Admin đã trừ <b>{format_vnd(amount)}</b> từ ví.\n💰 Số dư: <b>{format_vnd(new_balance)}</b>"
        else:
            msg = t("deposit_success", user.get("language", "vi"), amount=format_vnd(amount), balance=format_vnd(new_balance))
        await context.bot.send_message(chat_id=target_id, text=msg, parse_mode="HTML")
    except Exception:
        pass

    context.user_data.pop("quickcredit_target", None)
    context.user_data.pop("quickcredit_debit", None)
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END

@error_handler
@ensure_user
@admin_only
async def credit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(t("admin_credit_prompt", "vi"), parse_mode="HTML")
    context.user_data["active_conv"] = "admin_credit"
    return CREDIT_INPUT

@error_handler
@ensure_user
@admin_only
async def credit_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("active_conv") != "admin_credit":
        return ConversationHandler.END

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

    try:
        user_lang = user.get("language", "vi")
        await context.bot.send_message(
            chat_id=user_id,
            text=t("deposit_success", user_lang,
                amount=format_vnd(amount),
                balance=format_vnd(new_balance),
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    return ConversationHandler.END
