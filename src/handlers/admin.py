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
NOTE_INPUT = 14
CUSTOM_NAME = 15
CUSTOM_PRICE = 16
CUSTOM_EDIT_PRICE = 17
CUSTOM_EDIT_MENU = 18
CUSTOM_EDIT_NAME = 19


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
        is_active = m.get("is_active", 1)
        
        status_icon = "🟢" if is_active else "🔴"
        
        # Đảm bảo lãi tối thiểu 10k HOẶC 20%
        min_sell = max(cost + 10000, int(cost * 1.20))
        calc_sell = int(cost * (1 + pct / 100))
        calc_sell = max(calc_sell, min_sell)

        if fixed and fixed > 0:
            sell = max(fixed, min_sell)
            mode = "Cố định"
        else:
            sell = calc_sell
            mode = f"{pct}%"

        text += f"{status_icon} <b>{name}</b>\n"
        text += f"   Gốc: {format_vnd(cost)} → Bán: <b>{format_vnd(sell)}</b> ({mode})\n"

        btn_text = f"{status_icon} {name} | {format_vnd(sell)}"
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
    
    db = context.bot_data["db"]
    m_row = await db._fetch_one("SELECT is_active FROM product_markups WHERE product_id = ?", (product_id,))
    is_active = m_row["is_active"] if m_row else 1
    status_text = "🟢 Đang hiển thị" if is_active else "🔴 Đã bị ẩn"
    
    min_sell = max(cost + 10000, int(cost * 1.20))
    
    current_note = await db.get_custom_note(product_id)
    note_preview = f"\n📌 Ghi chú: <i>{current_note[:80]}{'...' if len(current_note) > 80 else ''}</i>" if current_note else "\n📌 Ghi chú: <i>(chưa có)</i>"

    text = (
        f"Bạn đang đổi giá cho: <b>{name}</b>\n"
        f"Trạng thái: <b>{status_text}</b>\n"
        f"💰 Giá gốc hệ thống: <b>{format_vnd(cost)}</b>\n"
        f"🛡️ Giá bán tối thiểu: <b>{format_vnd(min_sell)}</b>"
        f"{note_preview}\n\n"
        f"Nhập <b>% Markup</b> (ví dụ: <code>20</code>)\n"
        f"Hoặc nhập <b>Giá cố định</b> (kèm dấu =, ví dụ: <code>={min_sell}</code>):"
    )
    
    toggle_btn_text = "🔴 Ẩn sản phẩm" if is_active else "🟢 Hiện sản phẩm"
    keyboard = [
        [InlineKeyboardButton("📝 Sửa ghi chú", callback_data=f"admin:note_edit:{product_id}")],
        [InlineKeyboardButton(toggle_btn_text, callback_data=f"admin:markup_toggle:{product_id}")],
        [InlineKeyboardButton("⬅️ Hủy đổi giá", callback_data="admin:markup")]
    ]
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
        min_sell = max(cost + 10000, int(cost * 1.20))
        actual_sell = max(fixed_price, min_sell)
        
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
            min_sell = max(cost + 10000, int(cost * 1.20))
            actual_sell = max(calc_sell, min_sell)
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


@error_handler
@ensure_user
@admin_only
async def markup_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # query.answer() is handled in markup_prompt
    
    parts = query.data.split(":")
    if len(parts) < 3:
        return MARKUP_INPUT
        
    product_id = parts[2]
    context.user_data["admin_markup_product_id"] = product_id
    
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    
    row = await db._fetch_one("SELECT is_active FROM product_markups WHERE product_id = ?", (product_id,))
    current_active = row["is_active"] if row else 1
    new_active = 0 if current_active else 1
    
    product = canboso.find_product(product_id)
    name = product.get("product_name", product_id) if product else product_id
    
    await db.toggle_markup_active(product_id, name, new_active)
    
    # Re-render prompt with new state
    return await markup_prompt(update, context)


@error_handler
@ensure_user
@admin_only
async def note_edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    product_id = parts[2]
    context.user_data["admin_note_product_id"] = product_id

    canboso = context.bot_data["canboso"]
    db = context.bot_data["db"]
    product = canboso.find_product(product_id)
    name = product.get("product_name", product_id) if product else product_id

    current_note = await db.get_custom_note(product_id)
    note_display = current_note if current_note else "(chưa có)"

    text = (
        f"📝 <b>Sửa ghi chú cho: {name}</b>\n\n"
        f"Ghi chú hiện tại:\n<i>{note_display}</i>\n\n"
        f"Nhập ghi chú mới (hoặc gõ <code>xoa</code> để xóa):"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Hủy", callback_data="admin:markup")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    context.user_data["active_conv"] = "admin_note"
    return NOTE_INPUT


@error_handler
@ensure_user
@admin_only
async def note_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("active_conv") != "admin_note":
        return ConversationHandler.END

    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    product_id = context.user_data.get("admin_note_product_id")
    if not product_id:
        return ConversationHandler.END

    product = canboso.find_product(product_id)
    name = product.get("product_name", product_id) if product else product_id
    note_text = update.message.text.strip()

    if note_text.lower() == "xoa":
        await db.set_custom_note(product_id, name, "")
        await update.message.reply_text(
            f"✅ Đã xóa ghi chú cho <b>{name}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
    else:
        await db.set_custom_note(product_id, name, note_text)
        await update.message.reply_text(
            f"✅ Đã lưu ghi chú cho <b>{name}</b>:\n\n📌 {note_text}",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )

    context.user_data.pop("admin_note_product_id", None)
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


# ── Custom Products Admin ─────────────────────────────────────

@error_handler
@ensure_user
@admin_only
async def custom_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all custom products for admin."""
    query = update.callback_query
    await query.answer()

    db = context.bot_data["db"]
    products = await db.get_custom_products()

    text = "📦 <b>Sản phẩm Custom</b>\n\n"
    keyboard = []

    if products:
        for p in products:
            text += f"• <b>{p['name']}</b> — {format_vnd(p['price'])}\n"
            keyboard.append([
                InlineKeyboardButton(f"✏️ {p['name']}", callback_data=f"admin:custom_edit:{p['id']}"),
                InlineKeyboardButton("❌", callback_data=f"admin:custom_del:{p['id']}"),
            ])
    else:
        text += "Chưa có sản phẩm nào.\n"

    keyboard.append([InlineKeyboardButton("➕ Thêm SP mới", callback_data="admin:custom_add")])
    keyboard.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:refresh")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@error_handler
@ensure_user
@admin_only
async def custom_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a custom product — ask for name."""
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("⬅️ Hủy", callback_data="admin:custom")]]
    await query.edit_message_text(
        "➕ <b>Thêm sản phẩm mới</b>\n\nNhập <b>tên sản phẩm</b>:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_custom_add"
    return CUSTOM_NAME


@error_handler
@ensure_user
@admin_only
async def custom_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive product name, ask for price."""
    if context.user_data.get("active_conv") != "admin_custom_add":
        return ConversationHandler.END

    name = update.message.text.strip()
    context.user_data["custom_product_name"] = name

    await update.message.reply_text(
        f"Tên: <b>{name}</b>\n\nNhập <b>giá bán</b> (VND, ví dụ: <code>300000</code>):",
        parse_mode="HTML",
    )
    return CUSTOM_PRICE


@error_handler
@ensure_user
@admin_only
async def custom_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive price and save product."""
    if context.user_data.get("active_conv") != "admin_custom_add":
        return ConversationHandler.END

    try:
        price = int(update.message.text.strip().replace(",", "").replace(".", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Giá không hợp lệ. Nhập số dương, ví dụ: <code>300000</code>", parse_mode="HTML")
        return CUSTOM_PRICE

    db = context.bot_data["db"]
    name = context.user_data.pop("custom_product_name", "")
    product = await db.add_custom_product(name, price)

    await update.message.reply_text(
        f"✅ Đã thêm: <b>{product['name']}</b>\n💰 Giá: <b>{format_vnd(product['price'])}</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


@error_handler
@ensure_user
@admin_only
async def custom_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show edit menu with options to edit name or price."""
    query = update.callback_query
    await query.answer()

    if update.callback_query.data.startswith("admin:custom_edit:"):
        parts = query.data.split(":")
        product_id = int(parts[2])
        context.user_data["custom_edit_id"] = product_id
    else:
        product_id = context.user_data.get("custom_edit_id")

    db = context.bot_data["db"]
    product = await db.get_custom_product(product_id)
    if not product:
        await query.edit_message_text("❌ SP không tồn tại.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("✏️ Sửa tên", callback_data="admin:custom_edit_name"),
         InlineKeyboardButton("💰 Sửa giá", callback_data="admin:custom_edit_price")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:custom")]
    ]
    await query.edit_message_text(
        f"✏️ <b>Sửa sản phẩm: {product['name']}</b>\n"
        f"💰 Giá hiện tại: <b>{format_vnd(product['price'])}</b>\n\n"
        f"Bạn muốn thay đổi thông tin nào?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_custom_edit_menu"
    return CUSTOM_EDIT_MENU


@error_handler
@ensure_user
@admin_only
async def custom_edit_name_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for new name."""
    query = update.callback_query
    await query.answer()

    product_id = context.user_data.get("custom_edit_id")
    db = context.bot_data["db"]
    product = await db.get_custom_product(product_id)

    keyboard = [[InlineKeyboardButton("⬅️ Hủy", callback_data="admin:custom_edit_menu")]]
    await query.edit_message_text(
        f"✏️ <b>Sửa tên: {product['name']}</b>\n\n"
        f"Nhập tên mới cho sản phẩm này:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_custom_edit_name"
    return CUSTOM_EDIT_NAME


@error_handler
@ensure_user
@admin_only
async def custom_edit_price_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for new price."""
    query = update.callback_query
    await query.answer()

    product_id = context.user_data.get("custom_edit_id")
    db = context.bot_data["db"]
    product = await db.get_custom_product(product_id)

    keyboard = [[InlineKeyboardButton("⬅️ Hủy", callback_data="admin:custom_edit_menu")]]
    await query.edit_message_text(
        f"💰 <b>Sửa giá: {product['name']}</b>\n"
        f"Giá hiện tại: <b>{format_vnd(product['price'])}</b>\n\n"
        f"Nhập giá mới (VND):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_custom_edit_price"
    return CUSTOM_EDIT_PRICE


@error_handler
@ensure_user
@admin_only
async def custom_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new name."""
    if context.user_data.get("active_conv") != "admin_custom_edit_name":
        return ConversationHandler.END

    new_name = update.message.text.strip()
    db = context.bot_data["db"]
    product_id = context.user_data.pop("custom_edit_id", None)
    
    if not product_id:
        return ConversationHandler.END

    await db.update_custom_product(product_id, name=new_name)
    product = await db.get_custom_product(product_id)

    await update.message.reply_text(
        f"✅ <b>Đã đổi tên thành:</b> {product['name']}",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


@error_handler
@ensure_user
@admin_only
async def custom_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new price."""
    if context.user_data.get("active_conv") != "admin_custom_edit_price":
        return ConversationHandler.END

    try:
        price = int(update.message.text.strip().replace(",", "").replace(".", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Giá không hợp lệ.", parse_mode="HTML")
        return CUSTOM_EDIT_PRICE

    db = context.bot_data["db"]
    product_id = context.user_data.pop("custom_edit_id", None)
    if not product_id:
        return ConversationHandler.END

    product = await db.get_custom_product(product_id)
    await db.update_custom_product(product_id, price=price)

    await update.message.reply_text(
        f"✅ <b>{product['name']}</b>\nGiá mới: <b>{format_vnd(price)}</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


@error_handler
@ensure_user
@admin_only
async def custom_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a custom product."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    product_id = int(parts[2])

    db = context.bot_data["db"]
    product = await db.get_custom_product(product_id)
    if product:
        await db.delete_custom_product(product_id)
        await query.edit_message_text(
            f"🗑 Đã xóa: <b>{product['name']}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text("❌ SP không tồn tại.")


def get_admin_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broadcast_start, pattern=r"^admin:broadcast$"),
            CallbackQueryHandler(credit_start, pattern=r"^admin:credit$"),
            CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            CallbackQueryHandler(custom_add_start, pattern=r"^admin:custom_add$"),
            CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit:\d+$"),
            CallbackQueryHandler(custom_delete, pattern=r"^admin:custom_del:\d+$"),
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
                CallbackQueryHandler(note_edit_prompt, pattern=r"^admin:note_edit:.*$"),
                CallbackQueryHandler(markup_toggle, pattern=r"^admin:markup_toggle:.*$"),
                CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            ],
            NOTE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, note_save),
                CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            ],
            CUSTOM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_add_name),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_add_price),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_EDIT_MENU: [
                CallbackQueryHandler(custom_edit_name_prompt, pattern=r"^admin:custom_edit_name$"),
                CallbackQueryHandler(custom_edit_price_prompt, pattern=r"^admin:custom_edit_price$"),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_edit_name),
                CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit_menu$"),
            ],
            CUSTOM_EDIT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_edit_price),
                CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit_menu$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(admin_cancel, pattern=r"^(menu:|admin:refresh)"),
        ],
        per_message=False,
        allow_reentry=True,
    )
