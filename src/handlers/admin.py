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
MARKUP_SELECT = 13


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
    context.user_data["active_conv"] = "admin_broadcast"
    return BROADCAST_MESSAGE


@error_handler
@ensure_user
@admin_only
async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("active_conv") != "admin_broadcast":
        return ConversationHandler.END

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
    markup_map = {m["product_id"]: m for m in markups}

    text = "💰 <b>Markup Settings</b>\n\n"
    text += f"Mặc định: {config.default_markup_percent}%\n"
    text += "━━━━━━━━━━━━━━━━━━\n"

    keyboard = []

    for p in products:
        pid = p.get("_id", "")
        name = p.get("product_name", "")
        cost = p.get("walletPricing", 0)

        m = markup_map.get(pid, {})
        fixed = m.get("fixed_price", 0)
        pct = m.get("markup_percent", config.default_markup_percent)
        
        # Đảm bảo lãi tối thiểu 10.000đ
        min_sell = cost + 10000
        calc_sell = int(cost * (1 + pct / 100))
        calc_sell = max(calc_sell, min_sell)

        if fixed and fixed > 0:
            sell = max(fixed, calc_sell)
            mode = "Cố định"
        else:
            sell = calc_sell
            mode = f"{pct}%"

        text += f"📦 <b>{name}</b>\n"
        text += f"   Gốc: {format_vnd(cost)} → Bán: <b>{format_vnd(sell)}</b> ({mode})\n"

        btn_text = f"{name} | {format_vnd(cost)} → {format_vnd(sell)}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"admin:markup_select:{pid}")])

    text += "━━━━━━━━━━━━━━━━━━\n"
    text += "👇 <b>CHỌN SẢN PHẨM ĐỂ ĐỔI GIÁ:</b>"

    keyboard.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:refresh")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return MARKUP_SELECT


@error_handler
@ensure_user
@admin_only
async def markup_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) < 3:
        return MARKUP_SELECT
    
    product_id = parts[2]
    context.user_data["admin_markup_product_id"] = product_id
    
    canboso = context.bot_data["canboso"]
    product = canboso.find_product(product_id)
    if not product:
        await query.edit_message_text("❌ Không tìm thấy sản phẩm.")
        return ConversationHandler.END

    name = product.get("product_name", product_id)
    cost = product.get("walletPricing", 0)

    text = (
        f"Bạn đang đổi giá cho: <b>{name}</b>\n"
        f"💰 Giá gốc hệ thống: <b>{format_vnd(cost)}</b>\n\n"
        f"Nhập <b>% Markup</b> (ví dụ: <code>20</code>)\n"
        f"Hoặc nhập <b>Giá cố định</b> (kèm dấu =, ví dụ: <code>=25000</code>):"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Hủy đổi giá", callback_data="admin:markup")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    context.user_data["active_conv"] = "admin_markup"
    return MARKUP_INPUT


@error_handler
@ensure_user
@admin_only
async def markup_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    if context.user_data.get("active_conv") != "admin_markup":
        return ConversationHandler.END

    product_id = context.user_data.get("admin_markup_product_id")
    if not product_id:
        return ConversationHandler.END

    value = update.message.text.strip().replace(",", "").replace(".", "")

    product = canboso.find_product(product_id)
    name = product.get("product_name", product_id) if product else product_id
    cost = product.get("walletPricing", 0) if product else 0

    if value.startswith("="):
        # Fixed price mode
        try:
            fixed_price = int(value[1:])
        except ValueError:
            await update.message.reply_text("❌ Giá không hợp lệ. VD: <code>=25000</code>", parse_mode="HTML")
            return MARKUP_INPUT

        if cost > 0 and fixed_price <= cost:
            await update.message.reply_text(
                f"❌ Giá bán ({format_vnd(fixed_price)}) phải <b>cao hơn</b> giá gốc ({format_vnd(cost)}). Thử lại:",
                parse_mode="HTML",
            )
            return MARKUP_INPUT

        await db.set_markup(product_id, name, 0, fixed_price)
        
        # Calculate actual sell price applied
        actual_sell = max(fixed_price, cost + 10000)
        
        await update.message.reply_text(
            f"✅ <b>{name}</b>\nGiá cố định đã nhập: {format_vnd(fixed_price)}\nThực tế bán: <b>{format_vnd(actual_sell)}</b> (Gốc: {format_vnd(cost)})",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
    else:
        # Percentage mode
        try:
            markup = int(value)
        except ValueError:
            await update.message.reply_text("❌ Markup % không hợp lệ. VD: <code>20</code>", parse_mode="HTML")
            return MARKUP_INPUT

        await db.set_markup(product_id, name, markup, 0)
        
        if cost:
            calc_sell = int(cost * (1 + markup / 100))
            actual_sell = max(calc_sell, cost + 10000)
            sell_str = format_vnd(actual_sell)
        else:
            sell_str = "N/A"

        await update.message.reply_text(
            f"✅ <b>{name}</b>\nMarkup: {markup}% → Giá bán: <b>{sell_str}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )

    context.user_data.pop("admin_markup_product_id", None)
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.pop("active_conv", None)
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
            MARKUP_SELECT: [
                CallbackQueryHandler(markup_prompt, pattern=r"^admin:markup_select:.*$"),
                CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            ],
            MARKUP_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, markup_set),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(admin_cancel, pattern=r"^(menu:|admin:refresh)"),
        ],
        per_message=False,
        allow_reentry=True,
    )
