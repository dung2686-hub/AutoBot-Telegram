from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.handlers.shop import calc_min_sell, calc_sell_price, get_tier_markup
from src.config import config
from src.utils.decorators import ensure_user, admin_only, error_handler
from src.utils.formatters import format_vnd, esc
from src.utils.keyboards import admin_keyboard
from .states import MARKUP_SELECT, MARKUP_INPUT, NOTE_INPUT

@error_handler
@ensure_user
@admin_only
async def markup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    from src.handlers.shop import calc_min_sell
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    products = await canboso.get_products()
    markups = await db.get_all_markups()
    markup_map = {m["product_id"]: m for m in markups}

    text = "💰 <b>Markup Settings</b>\n\n"
    text += "Bậc thang: &lt;100k (30%), ≥100k (25%)\n"
    text += "━━━━━━━━━━━━━━━━━━\n"

    keyboard = []

    for p in products:
        pid = p.get("_id", "")
        name = p.get("product_name", "")
        cost = p.get("walletPricing", 0)

        m = markup_map.get(pid, {})
        fixed = m.get("fixed_price", 0)
        tier_pct = get_tier_markup(cost)
        pct = m.get("markup_percent", tier_pct)
        is_active = m.get("is_active", 1)
        
        status_icon = "🟢" if is_active else "🔴"
        
        min_sell = calc_min_sell(cost)
        calc_sell = int(cost * (1 + pct / 100))
        calc_sell = max(calc_sell, min_sell)

        if fixed and fixed > 0:
            sell = max(fixed, min_sell)
            mode = "Cố định"
        else:
            sell = calc_sell
            mode = f"{pct}%"

        text += f"{status_icon} <b>{esc(name)}</b>\n"
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
    is_active = await db.get_product_markup_status(product_id)
    status_text = "🟢 Đang hiển thị" if is_active else "🔴 Đã bị ẩn"
    
    sell_price = await calc_sell_price(db, product_id, cost)
    min_sell = calc_min_sell(cost)
    tier_pct = get_tier_markup(cost)
    m = await db.get_markup(product_id, tier_pct)
    if m["fixed_price"] > 0:
        price_mode_str = "Cố định"
    else:
        price_mode_str = f"Markup {m['markup_percent']}%"
    
    current_note = await db.get_custom_note(product_id)
    note_preview = f"\n📌 Ghi chú: <i>{esc(current_note[:80])}{'...' if len(current_note) > 80 else ''}</i>" if current_note else "\n📌 Ghi chú: <i>(chưa có)</i>"

    text = (
        f"Bạn đang đổi giá cho: <b>{esc(name)}</b>\n"
        f"Trạng thái: <b>{status_text}</b>\n"
        f"💰 Giá gốc hệ thống: <b>{format_vnd(cost)}</b>\n"
        f"🛡️ Giá bán tối thiểu: <b>{format_vnd(min_sell)}</b>\n"
        f"💵 Giá bán HIỆN TẠI: <b>{format_vnd(sell_price)}</b> ({price_mode_str})"
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
        
        min_sell = calc_min_sell(cost)
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
            min_sell = calc_min_sell(cost)
            actual_sell = max(calc_sell, min_sell)
            sell_str = format_vnd(actual_sell)
        else:
            sell_str = "N/A"

        await update.message.reply_text(
            f"✅ <b>{esc(name)}</b>\nMarkup: {markup}% → Giá bán: <b>{sell_str}</b>",
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
    
    parts = query.data.split(":")
    if len(parts) < 3:
        return MARKUP_INPUT
        
    product_id = parts[2]
    context.user_data["admin_markup_product_id"] = product_id
    
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    
    is_active = await db.get_product_markup_status(product_id)
    new_active = 0 if is_active else 1
    
    product = canboso.find_product(product_id)
    name = product.get("product_name", product_id) if product else product_id
    
    await db.toggle_markup_active(product_id, name, new_active)
    
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
        f"📝 <b>Sửa ghi chú cho: {esc(name)}</b>\n\n"
        f"Ghi chú hiện tại:\n<i>{esc(note_display)}</i>\n\n"
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
            f"✅ Đã xóa ghi chú cho <b>{esc(name)}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
    else:
        await db.set_custom_note(product_id, name, note_text)
        await update.message.reply_text(
            f"✅ Đã lưu ghi chú cho <b>{esc(name)}</b>:\n\n📌 {esc(note_text)}",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )

    context.user_data.pop("admin_note_product_id", None)
    return ConversationHandler.END
