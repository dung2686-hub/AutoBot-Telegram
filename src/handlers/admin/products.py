from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.utils.decorators import ensure_user, admin_only, error_handler
from src.utils.formatters import format_vnd, esc
from src.utils.keyboards import admin_keyboard
from .states import CUSTOM_NAME, CUSTOM_PRICE, CUSTOM_EDIT_PRICE, CUSTOM_EDIT_MENU, CUSTOM_EDIT_NAME, CUSTOM_EDIT_STOCK, CUSTOM_EDIT_NOTE, CUSTOM_ADD_STOCK, CUSTOM_ADD_NOTE

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
            stock = p.get("stock", 0)
            note_status = "✅" if p.get("delivery_note") else "❌"
            text += f"• <b>{esc(p['name'])}</b> — {format_vnd(p['price'])} | 📦 {stock} | Note: {note_status}\n"
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
        f"Tên: <b>{esc(name)}</b>\n\nNhập <b>giá bán</b> (VND, ví dụ: <code>300000</code>):",
        parse_mode="HTML",
    )
    return CUSTOM_PRICE

@error_handler
@ensure_user
@admin_only
async def custom_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive price, ask for stock."""
    if context.user_data.get("active_conv") != "admin_custom_add":
        return ConversationHandler.END

    try:
        price = int(update.message.text.strip().replace(",", "").replace(".", ""))
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Giá không hợp lệ. Nhập số dương, ví dụ: <code>300000</code>", parse_mode="HTML")
        return CUSTOM_PRICE

    context.user_data["custom_product_price"] = price
    name = context.user_data.get("custom_product_name", "")

    await update.message.reply_text(
        f"Tên: <b>{esc(name)}</b>\n"
        f"Giá: <b>{format_vnd(price)}</b>\n\n"
        f"Nhập <b>số lượng tồn kho</b> (VD: <code>10</code>):",
        parse_mode="HTML",
    )
    return CUSTOM_ADD_STOCK


@error_handler
@ensure_user
@admin_only
async def custom_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive stock, ask for delivery note."""
    if context.user_data.get("active_conv") != "admin_custom_add":
        return ConversationHandler.END

    try:
        stock = int(update.message.text.strip().replace(",", "").replace(".", ""))
        if stock < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Số không hợp lệ. Nhập số >= 0.", parse_mode="HTML")
        return CUSTOM_ADD_STOCK

    context.user_data["custom_product_stock"] = stock

    keyboard = [[InlineKeyboardButton("⏭ Bỏ qua", callback_data="admin:custom_skip_note")]]
    await update.message.reply_text(
        f"📦 Stock: <b>{stock}</b>\n\n"
        f"Nhập <b>ghi chú giao hàng</b> (hiển thị cho khách sau thanh toán).\n"
        f"VD: <i>Liên hệ Zalo 0988660809 để nhận tài khoản</i>\n\n"
        f"Hoặc bấm <b>Bỏ qua</b> nếu chưa cần.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return CUSTOM_ADD_NOTE


@error_handler
@ensure_user
@admin_only
async def custom_add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive delivery note, save product with all fields."""
    if context.user_data.get("active_conv") != "admin_custom_add":
        return ConversationHandler.END

    note = update.message.text.strip()
    await _save_new_custom_product(context, update, note=note)
    return ConversationHandler.END


@error_handler
@ensure_user
@admin_only
async def custom_add_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip delivery note, save product without it."""
    query = update.callback_query
    await query.answer()

    await _save_new_custom_product(context, update, note="")
    return ConversationHandler.END


async def _save_new_custom_product(context, update, note: str):
    """Save custom product with all collected fields."""
    import logging
    _logger = logging.getLogger(__name__)

    db = context.bot_data["db"]
    name = context.user_data.pop("custom_product_name", "")
    price = context.user_data.pop("custom_product_price", 0)
    stock = context.user_data.pop("custom_product_stock", 0)
    context.user_data.pop("active_conv", None)

    _logger.info("Creating custom product: name=%s, price=%d, stock=%d, note=%s", name, price, stock, note[:30] if note else "")

    product = await db.add_custom_product(name, price, stock)
    _logger.info("Product created: id=%d", product["id"])

    if note:
        await db.update_custom_product(product["id"], delivery_note=note)
        _logger.info("Delivery note saved for product %d", product["id"])

    text = (
        f"✅ <b>Đã thêm sản phẩm:</b>\n\n"
        f"📦 Tên: <b>{esc(product['name'])}</b>\n"
        f"💰 Giá: <b>{format_vnd(product['price'])}</b>\n"
        f"📦 Stock: <b>{stock}</b>\n"
        f"📝 Ghi chú: <i>{esc(note[:80]) if note else 'Chưa có'}</i>"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=admin_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=admin_keyboard(), parse_mode="HTML")

@error_handler
@ensure_user
@admin_only
async def custom_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show edit menu with options to edit name, price, stock, or delivery note."""
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

    note_preview = (product.get("delivery_note") or "Chưa có")[:50]

    keyboard = [
        [InlineKeyboardButton("✏️ Sửa tên", callback_data="admin:custom_edit_name"),
         InlineKeyboardButton("💰 Sửa giá", callback_data="admin:custom_edit_price")],
        [InlineKeyboardButton("📦 Sửa stock", callback_data="admin:custom_edit_stock"),
         InlineKeyboardButton("📝 Sửa ghi chú", callback_data="admin:custom_edit_note")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:custom")]
    ]
    await query.edit_message_text(
        f"✏️ <b>Sửa sản phẩm: {esc(product['name'])}</b>\n"
        f"💰 Giá: <b>{format_vnd(product['price'])}</b>\n"
        f"📦 Stock: <b>{product.get('stock', 0)}</b>\n"
        f"📝 Ghi chú giao hàng: <i>{esc(note_preview)}</i>\n\n"
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
        f"✏️ <b>Sửa tên: {esc(product['name'])}</b>\n\n"
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
        f"💰 <b>Sửa giá: {esc(product['name'])}</b>\n"
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
        f"✅ <b>Đã đổi tên thành:</b> {esc(product['name'])}",
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
        f"✅ <b>{esc(product['name'])}</b>\nGiá mới: <b>{format_vnd(price)}</b>",
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
            f"🗑 Đã xóa: <b>{esc(product['name'])}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text("❌ SP không tồn tại.")

@error_handler
@ensure_user
@admin_only
async def custom_edit_stock_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for new stock count."""
    query = update.callback_query
    await query.answer()

    product_id = context.user_data.get("custom_edit_id")
    db = context.bot_data["db"]
    product = await db.get_custom_product(product_id)

    keyboard = [[InlineKeyboardButton("⬅️ Hủy", callback_data="admin:custom_edit_menu")]]
    await query.edit_message_text(
        f"📦 <b>Sửa stock: {esc(product['name'])}</b>\n"
        f"Stock hiện tại: <b>{product.get('stock', 0)}</b>\n\n"
        f"Nhập số lượng stock mới:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_custom_edit_stock"
    return CUSTOM_EDIT_STOCK

@error_handler
@ensure_user
@admin_only
async def custom_edit_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new stock count."""
    if context.user_data.get("active_conv") != "admin_custom_edit_stock":
        return ConversationHandler.END

    try:
        stock = int(update.message.text.strip().replace(",", "").replace(".", ""))
        if stock < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Số không hợp lệ. Nhập số >= 0.", parse_mode="HTML")
        return CUSTOM_EDIT_STOCK

    db = context.bot_data["db"]
    product_id = context.user_data.pop("custom_edit_id", None)
    if not product_id:
        return ConversationHandler.END

    product = await db.get_custom_product(product_id)
    await db.update_custom_product(product_id, stock=stock)

    await update.message.reply_text(
        f"✅ <b>{esc(product['name'])}</b>\nStock mới: <b>{stock}</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END

@error_handler
@ensure_user
@admin_only
async def custom_edit_note_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for new delivery note."""
    query = update.callback_query
    await query.answer()

    product_id = context.user_data.get("custom_edit_id")
    db = context.bot_data["db"]
    product = await db.get_custom_product(product_id)

    current_note = product.get("delivery_note", "") or "Chưa có"

    keyboard = [[InlineKeyboardButton("⬅️ Hủy", callback_data="admin:custom_edit_menu")]]
    await query.edit_message_text(
        f"📝 <b>Sửa ghi chú giao hàng: {esc(product['name'])}</b>\n\n"
        f"Ghi chú hiện tại:\n<i>{esc(current_note)}</i>\n\n"
        f"Nhập ghi chú mới (hiển thị cho khách sau khi thanh toán):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["active_conv"] = "admin_custom_edit_note"
    return CUSTOM_EDIT_NOTE

@error_handler
@ensure_user
@admin_only
async def custom_edit_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save new delivery note."""
    if context.user_data.get("active_conv") != "admin_custom_edit_note":
        return ConversationHandler.END

    note = update.message.text.strip()
    db = context.bot_data["db"]
    product_id = context.user_data.pop("custom_edit_id", None)
    if not product_id:
        return ConversationHandler.END

    product = await db.get_custom_product(product_id)
    await db.update_custom_product(product_id, delivery_note=note)

    await update.message.reply_text(
        f"✅ <b>{esc(product['name'])}</b>\n📝 Ghi chú mới:\n<i>{esc(note[:100])}</i>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END
