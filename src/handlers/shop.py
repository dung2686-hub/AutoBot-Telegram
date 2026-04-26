import logging
import math
import io
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.formatters import format_vnd, shorten_product_name, esc, format_account_list, now_vn
from src.utils.keyboards import product_detail_keyboard, back_to_menu_keyboard, confirm_cancel_keyboard, payment_options_keyboard
from src.services.vietqr import generate_qr_image, get_bank_display_name
from src.services.referral import process_referral_bonus

logger = logging.getLogger(__name__)


def _round_up_1000(price: int) -> int:
    """Làm tròn lên bội số 1000đ gần nhất. VD: 54200 → 55000."""
    return int(math.ceil(price / 1000) * 1000)


def get_tier_markup(cost_price: int) -> int:
    """Xác định tỷ lệ markup % dựa trên giá vốn."""
    if cost_price < 100000:
        return 30
    return 25


def calc_min_sell(cost_price: int) -> int:
    """Giá bán tối thiểu: lãi 15k hoặc % theo bậc thang, tùy cái nào lớn hơn."""
    tier_pct = get_tier_markup(cost_price)
    return max(cost_price + 15000, int(cost_price * (1 + tier_pct / 100)))


async def calc_sell_price(db, product_id: str, cost_price: int) -> int:
    """Calculate sell price from markup settings. Guarantees min 15k or tiered profit."""
    tier_pct = get_tier_markup(cost_price)
    m = await db.get_markup(product_id, tier_pct)

    # Sử dụng markup từ DB, nhưng ép sàn tối thiểu bằng tỷ lệ bậc thang
    effective_pct = max(m["markup_percent"], tier_pct)
    markup_price = int(cost_price * (1 + effective_pct / 100))

    min_sell = calc_min_sell(cost_price)
    markup_price = max(markup_price, min_sell)

    if m["fixed_price"] > 0:
        sell = max(m["fixed_price"], min_sell)
        if sell == min_sell:
            return _round_up_1000(sell)
        return sell
    return _round_up_1000(markup_price)


@error_handler
@ensure_user
async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product listing."""
    query = update.callback_query
    await query.answer()
    logger.info("[SHOP-MENU] entered by user %s", update.effective_user.id)

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    products = await canboso.get_products()
    if not products:
        await query.edit_message_text(
            t("shop_empty", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    inactive_ids = await db.get_inactive_product_ids()

    keyboard = []
    for p in products:
        if p.get("hiddenInBotMenu") or p.get("_id") in inactive_ids:
            continue
        name = p.get("product_name", "Unknown")
        price = p.get("walletPricing", 0)
        product_id = p.get("_id", "")

        sell_price = await calc_sell_price(db, product_id, price)

        stats = p.get("stats", {})
        available = stats.get("available")
        stock_text = f" ({available})" if available is not None else ""

        keyboard.append([
            InlineKeyboardButton(
                f"{shorten_product_name(name)} — {format_vnd(sell_price)}{stock_text}",
                callback_data=f"shop:detail:{product_id}",
            )
        ])

    custom_products = await db.get_custom_products()
    for p in custom_products:
        stock = p.get("stock", 0)
        stock_text = f" 📦 {stock}" if stock > 0 else " ❌ Hết"
        btn_text = f"🔑 {p['name']} — {format_vnd(p['price'])}{stock_text}"
        keyboard.append([
            InlineKeyboardButton(btn_text, callback_data=f"custom:detail:{p['id']}")
        ])

    keyboard.append([
        InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")
    ])

    await query.edit_message_text(
        t("shop_title", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


@error_handler
@ensure_user
async def product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product detail with quantity selector."""
    query = update.callback_query
    logger.info("[PRODUCT-DETAIL] >>> ENTERED by user %s, data=%s", update.effective_user.id, query.data)
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    # Always refresh to get latest stock
    logger.info("[PRODUCT-DETAIL] refreshing cache for product %s", product_id)
    await canboso.refresh_cache()
    product = canboso.find_product(product_id)
    logger.info("[PRODUCT-DETAIL] product found: %s", product is not None)

    if not product:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    sell_price = await calc_sell_price(db, product_id, product.get("walletPricing", 0))

    stats = product.get("stats", {})
    available = stats.get("available")

    # Cap quantity at available stock
    if available is not None and available > 0:
        quantity = min(quantity, available)
    elif available == 0:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    slot_info = ""
    if stats.get("total") is not None:
        slot_info = t("slot_info", lang,
            available=available or 0,
            total=stats.get("total", 0),
        )

    # Get shop custom note
    custom_note = await db.get_custom_note(product_id)

    text = t("product_detail", lang,
        name=esc(shorten_product_name(product.get("product_name", ""))),
        description=esc(product.get("description", "")),
        price=format_vnd(sell_price),
        slot_info=slot_info,
        quantity=quantity,
    )

    if custom_note:
        text += f"\n\n📌 <b>Ghi chú từ shop:</b>\n{esc(custom_note)}"

    keyboard = product_detail_keyboard(product_id, quantity, lang, max_qty=available)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


@error_handler
@ensure_user
async def quantity_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity +/- buttons."""
    await product_detail(update, context)


@error_handler
@ensure_user
async def buy_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show purchase confirmation."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = canboso.find_product(product_id)
    if not product:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # Stock check
    available = product.get("stats", {}).get("available")
    if available is not None and quantity > available:
        await query.edit_message_text(
            f"⚠️ Số lượng yêu cầu vượt quá tồn kho ({available}). Vui lòng chọn lại.",
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    db_user = context.user_data["db_user"]
    sell_price = await calc_sell_price(db, product_id, product.get("walletPricing", 0))
    total = sell_price * quantity
    balance = db_user["balance"]

    text = t("confirm_purchase", lang,
        name=esc(product.get("product_name", "")),
        quantity=quantity,
        price=format_vnd(sell_price),
        total=format_vnd(total),
        balance=format_vnd(balance),
    )

    keyboard = payment_options_keyboard(product_id, quantity, lang)
    
    # Prompt the user to select a payment method
    text += "\n\n<b>Vui lòng chọn phương thức thanh toán:</b>"
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

@error_handler
@ensure_user
async def qr_pay_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate QR and Pending Order for Direct Pay."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    telegram_id = update.effective_user.id
    db_user = context.user_data["db_user"]

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = canboso.find_product(product_id)
    if not product:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    sell_price = await calc_sell_price(db, product_id, product.get("walletPricing", 0))
    total = sell_price * quantity

    # Create a pending order
    order = await db.create_order(
        user_id=db_user["id"],
        product_id=product_id,
        product_name=product.get("product_name", ""),
        quantity=quantity,
        original_price=product.get("walletPricing", 0),
        sell_price=sell_price,
        order_code="",
        delivered_data=[],
        status="pending"
    )
    
    order_id = order["id"]
    order_code_mem = f"MUA{order_id}"

    # Validate bank config
    if not config.bank_bin or not config.bank_account:
        await query.edit_message_text(
            "⚠️ Admin chưa cấu hình thanh toán ngân hàng. Vui lòng nạp ví trước.",
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # Generate QR with 3-tier fallback
    qr_bytes = await generate_qr_image(total, order_code_mem)
    bank_display = get_bank_display_name(config.bank_bin)

    msg_text = (
        f"🏦 <b>Chuyển khoản tới {bank_display} - {config.bank_account}</b>\n"
        f"👤 Chủ TK: <b>{esc(config.bank_account_name)}</b>\n\n"
        f"💰 Số tiền: <b>{format_vnd(total)}</b>\n"
        f"📝 Nội dung CK: <code>{esc(order_code_mem)}</code>\n"
        f"⏰ Thời gian còn lại: <b>5 phút</b>\n\n"
        f"📱 Quét mã QR bên dưới để chuyển khoản.\n"
        f"⚠️ <b>Lưu ý:</b> Nhập đúng nội dung chuyển khoản!"
    )

    await query.message.delete()
    await context.bot.send_photo(
        chat_id=telegram_id,
        photo=qr_bytes,
        caption=msg_text,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(lang)
    )


@error_handler
@ensure_user
async def execute_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the actual purchase via Canboso API."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id

    # Double-click protection
    processing = context.bot_data.setdefault("_processing_purchases", set())
    if telegram_id in processing:
        await query.answer("⏳ Đang xử lý đơn hàng, vui lòng chờ...", show_alert=True)
        return
    processing.add(telegram_id)

    try:
        await _do_execute_purchase(update, context, query, telegram_id)
    finally:
        processing.discard(telegram_id)


async def _do_execute_purchase(update, context, query, telegram_id):
    """Internal purchase logic (separated for double-click protection)."""
    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    db_user = context.user_data["db_user"]

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = canboso.find_product(product_id)
    if not product:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    sell_price = await calc_sell_price(db, product_id, product.get("walletPricing", 0))
    total = sell_price * quantity

    # Check balance
    current_balance = await db.get_balance(telegram_id)
    if current_balance < total:
        await query.edit_message_text(
            t("purchase_insufficient", lang,
                balance=format_vnd(current_balance),
                total=format_vnd(total),
            ),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # --- PROTECT AGAINST PRICE SLIPPAGE ---
    await canboso.refresh_cache()
    product = canboso.find_product(product_id)
    current_cost = product.get("walletPricing", 0) if product else float('inf')
    
    if not product or current_cost > sell_price:
        await query.edit_message_text(
            "❌ <b>Sản phẩm tạm thời đổi giá hoặc ngừng bán từ hệ thống tổng. Giao dịch đã bị hủy để bảo vệ số dư của bạn!</b>",
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # Call Canboso API
    # Deduct balance (atomic — prevents race condition)
    logger.info("[WALLET-PURCHASE] Deducting %s from user %s", total, telegram_id)
    new_balance = await db.update_balance(telegram_id, -total)
    if new_balance == -1:
        await query.edit_message_text(
            t("purchase_insufficient", lang,
                balance=format_vnd(await db.get_balance(telegram_id)),
                total=format_vnd(total),
            ),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    user = await db.get_user(telegram_id)
    try:
        order = await db.create_order(
            user_id=user["id"],
            order_code="",
            product_id=product_id,
            product_name=product.get("product_name", ""),
            quantity=quantity,
            original_price=product.get("walletPricing", 0),
            sell_price=sell_price,
            delivered_data=[],
            status="pending",
        )
    except Exception:
        refund_balance = await db.update_balance(telegram_id, total)
        logger.exception("[WALLET-PURCHASE] Failed to create pending order, refunded user %s", telegram_id)
        try:
            await db.add_transaction(
                user_id=user["id"],
                tx_type="refund",
                amount=total,
                balance_after=refund_balance,
                description="Hoàn tiền do lỗi tạo đơn hàng",
            )
        except Exception:
            logger.exception("[WALLET-PURCHASE] Failed to log refund after order creation error")
        await query.edit_message_text(
            t("purchase_error", lang, error="Internal order creation failed"),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    try:
        result = await canboso.purchase(
            product_id=product_id,
            quantity=quantity,
        )
    except Exception as e:
        refund_balance = await db.update_balance(telegram_id, total)
        await db.update_order(order["id"], status="failed")
        await db.add_transaction(
            user_id=user["id"],
            tx_type="refund",
            amount=total,
            balance_after=refund_balance,
            description=f"Hoàn tiền do lỗi kết nối nguồn ({order['id']})",
            reference_id=str(order["id"]),
        )
        logger.exception("[WALLET-PURCHASE] Provider call crashed for user %s: %s", telegram_id, e)
        await query.edit_message_text(
            t("purchase_error", lang, error="Provider request failed"),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    if not result.get("success"):
        error_msg = result.get("message", "Unknown error")
        refund_balance = await db.update_balance(telegram_id, total)
        await db.update_order(order["id"], status="failed")
        await db.add_transaction(
            user_id=user["id"],
            tx_type="refund",
            amount=total,
            balance_after=refund_balance,
            description=f"Hoàn tiền do lỗi mua hàng ({order['id']})",
            reference_id=str(order["id"]),
        )
        await query.edit_message_text(
            t("purchase_error", lang, error=error_msg),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    delivered = result.get("deliveredAccounts", [])
    await db.update_order(
        order["id"],
        status="completed",
        order_code=result.get("orderCode", ""),
        delivered_data=delivered,
    )
    await db.add_transaction(
        user_id=user["id"],
        tx_type="purchase",
        amount=-total,
        balance_after=new_balance,
        description=f"Mua {product.get('product_name', '')} x{quantity}",
        reference_id=str(order["id"]),
    )

    # Referral bonus disabled — uncomment to re-enable
    # await process_referral_bonus(db, context.application, order["id"], user["id"], total)

    # === SEND RESULT — use send_message (same as QR flow which works) ===
    accounts_text = format_account_list(delivered, lang)

    text = t("purchase_success", lang,
        name=esc(product.get("product_name", "")),
        quantity=quantity,
        total=format_vnd(total),
        accounts=accounts_text,
    )
    text += f"\n💳 Số dư còn: {format_vnd(new_balance)}"

    # Delete old confirmation message (non-critical)
    try:
        await query.message.delete()
    except Exception:
        pass

    # Send NEW message (same approach as QR flow in sepay_webhook.py line 224)
    try:
        await context.bot.send_message(
            chat_id=telegram_id, text=text,
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        logger.info("[WALLET-PURCHASE] Success message sent to %s", telegram_id)
    except Exception as e:
        logger.error("[WALLET-PURCHASE] send_message HTML failed: %s", e)
        try:
            plain = f"✅ Mua hàng thành công!\n\n{accounts_text}\n\n💳 Số dư còn: {format_vnd(new_balance)}"
            await context.bot.send_message(chat_id=telegram_id, text=plain)
        except Exception as e2:
            logger.error("[WALLET-PURCHASE] ALL message attempts failed: %s", e2)

    # Refresh product cache (non-critical)
    try:
        await canboso.refresh_cache()
    except Exception:
        pass

    # === NOTIFY ADMIN: New wallet order ===
    if config.admin_chat_id:
        try:
            from src.utils.formatters import now_vn
            cost = product.get("walletPricing", 0) * quantity
            profit = total - cost
            time_str = now_vn().strftime("%H:%M %d/%m/%Y")
            admin_msg = (
                f"🛒 <b>ĐƠN HÀNG MỚI</b>\n\n"
                f"👤 Khách: {esc(user.get('full_name', 'N/A'))} (<code>{telegram_id}</code>)\n"
                f"📦 SP: {esc(product.get('product_name', ''))} x{quantity}\n"
                f"💰 Bán: {format_vnd(total)}\n"
                f"💵 Vốn: {format_vnd(cost)}\n"
                f"📊 Lãi: +{format_vnd(profit)}\n"
                f"💳 TT: Ví\n\n"
                f"⏰ {time_str}"
            )
            await context.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
        except Exception:
            pass


# ── Custom Products (Customer-facing) ─────────────────────


@error_handler
@ensure_user
async def custom_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show custom product detail with quantity selector (like Canboso flow)."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) < 3:
        return

    product_id = int(parts[2])
    quantity = int(parts[3]) if len(parts) > 3 else None  # None = first visit

    db = context.bot_data["db"]
    lang = context.user_data.get("lang", "vi")
    product = await db.get_custom_product(product_id)

    if not product or not product.get("is_active"):
        await query.edit_message_text(
            "❌ Sản phẩm không tồn tại hoặc đã ngưng bán.",
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    stock = product.get("stock", 0)
    if stock <= 0:
        await query.edit_message_text(
            f"❌ <b>{esc(product['name'])}</b> đã hết hàng.",
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # First visit → show quantity picker
    if quantity is None:
        text = (
            f"✅ Bạn đã chọn sản phẩm:\n"
            f"📦 <b>{esc(product['name'])}</b>\n"
            f"💰 Giá: <b>{format_vnd(product['price'])}</b> / tài khoản.\n"
            f"📦 Tồn kho: <b>{stock}</b> tài khoản.\n\n"
            f"👉 Nhập số lượng bạn muốn mua (từ 1 đến {stock}).\n"
            f"Hoặc bấm ❌ <b>Hủy chọn</b> để chọn sản phẩm khác."
        )
        keyboard = _custom_quantity_keyboard(product_id, stock, lang)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

    # Quantity selected → go to buy confirm
    quantity = min(quantity, stock)
    quantity = max(1, quantity)
    context.user_data["custom_buy"] = {"product_id": product_id, "quantity": quantity}
    await _show_custom_buy_confirm(query, context, product, quantity, lang)


def _custom_quantity_keyboard(product_id: int, max_qty: int, lang: str = "vi") -> InlineKeyboardMarkup:
    """Build quantity picker: 1/2/3, 5/10, custom input, back/close."""
    row1 = []
    for q in [1, 2, 3]:
        if q <= max_qty:
            row1.append(InlineKeyboardButton(str(q), callback_data=f"custom:detail:{product_id}:{q}"))
    row2 = []
    for q in [5, 10]:
        if q <= max_qty:
            row2.append(InlineKeyboardButton(str(q), callback_data=f"custom:detail:{product_id}:{q}"))

    rows = [row1]
    if row2:
        rows.append(row2)
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="menu:shop"),
                 InlineKeyboardButton("❌ Đóng", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


async def _show_custom_buy_confirm(query, context, product, quantity, lang):
    """Show payment summary for custom product."""
    db = context.bot_data["db"]
    db_user = context.user_data["db_user"]

    price = product["price"]
    total = price * quantity
    balance = db_user["balance"]
    shortfall = max(0, total - balance)

    text = (
        f"🔖 Thanh toán đơn hàng\n\n"
        f"📦 Sản phẩm: <b>{esc(product['name'])}</b>\n"
        f"📦 Số lượng: <b>{quantity}</b>\n"
        f"💰 Tạm tính: <b>{format_vnd(total)}</b>\n"
        f"🎁 Giảm giá: 0đ\n"
        f"💳 Cần thanh toán: <b>{format_vnd(total)}</b>\n"
        f"👛 Số dư ví: <b>{format_vnd(balance)}</b>\n"
        f"{'⚠️' if shortfall > 0 else '✅'} Còn thiếu: <b>{format_vnd(shortfall)}</b>"
    )

    product_id = product["id"]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Thanh toán bằng ví", callback_data=f"custom:execute:{product_id}:{quantity}")],
        [InlineKeyboardButton("🏦 Chuyển khoản QR", callback_data=f"custom:qr_pay:{product_id}:{quantity}")],
        [InlineKeyboardButton("❌ Hủy đơn", callback_data="menu:shop")],
    ])

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


@error_handler
@ensure_user
async def custom_execute_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute custom product purchase via wallet."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id

    # Double-click protection
    processing = context.bot_data.setdefault("_processing_purchases", set())
    if telegram_id in processing:
        await query.answer("⏳ Đang xử lý đơn hàng, vui lòng chờ...", show_alert=True)
        return
    processing.add(telegram_id)

    try:
        await _do_custom_execute(update, context, query, telegram_id)
    finally:
        processing.discard(telegram_id)


async def _do_custom_execute(update, context, query, telegram_id):
    """Internal custom purchase logic via wallet."""
    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    db_user = context.user_data["db_user"]

    parts = query.data.split(":")
    product_id = int(parts[2])
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = await db.get_custom_product(product_id)
    if not product or not product.get("is_active"):
        await query.edit_message_text(
            "❌ Sản phẩm không tồn tại.",
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    stock = product.get("stock", 0)
    if quantity > stock:
        await query.edit_message_text(
            f"⚠️ Số lượng yêu cầu vượt quá tồn kho ({stock}). Vui lòng chọn lại.",
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    price = product["price"]
    total = price * quantity

    # Check balance
    current_balance = await db.get_balance(telegram_id)
    if current_balance < total:
        await query.edit_message_text(
            f"❌ Số dư không đủ.\n\n"
            f"💳 Số dư: <b>{format_vnd(current_balance)}</b>\n"
            f"💰 Cần: <b>{format_vnd(total)}</b>\n\n"
            f"Vui lòng nạp thêm hoặc chọn <b>Chuyển khoản QR</b>.",
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    # Deduct balance (atomic)
    new_balance = await db.update_balance(telegram_id, -total)
    if new_balance == -1:
        await query.edit_message_text(
            "❌ Số dư không đủ.", reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    # Decrement stock
    stock_ok = await db.decrement_custom_stock(product_id, quantity)
    if not stock_ok:
        # Refund
        await db.update_balance(telegram_id, total)
        await query.edit_message_text(
            "❌ Sản phẩm đã hết hàng. Số tiền đã được hoàn lại.",
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    user = await db.get_user(telegram_id)
    # Create completed order
    order = await db.create_order(
        user_id=user["id"],
        product_id=f"custom_{product_id}",
        product_name=product["name"],
        quantity=quantity,
        original_price=price,
        sell_price=price,
        order_code="",
        delivered_data=[],
        status="completed",
    )

    await db.add_transaction(
        user_id=user["id"], tx_type="purchase", amount=-total,
        balance_after=new_balance,
        description=f"Mua {product['name']} x{quantity}",
        reference_id=str(order["id"]),
    )

    # Send success message
    delivery_note = product.get("delivery_note", "") or ""
    if not delivery_note:
        delivery_note = _default_delivery_note()

    order_date = now_vn().strftime("%d/%m/%Y")
    text = (
        f"🎉 <b>Thanh toán thành công!</b>\n\n"
        f"📋 Mã đơn: <b>ORD{order['id']}</b>\n"
        f"📦 Sản phẩm: <b>{esc(product['name'])}</b>\n"
        f"📦 Số lượng: <b>{quantity}</b>\n"
        f"📅 Ngày tạo: <b>{order_date}</b>\n\n"
        f"🔑 <b>Danh sách tài khoản:</b>\n"
        f"{esc(delivery_note)}\n\n"
        f"💳 Số dư còn: <b>{format_vnd(new_balance)}</b>"
    )

    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=telegram_id, text=text,
        reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
    )

    # Notify admin
    await _notify_admin_custom_order(context, user, product, quantity, total, order["id"], "Ví")


@error_handler
@ensure_user
async def custom_qr_pay_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate QR and pending order for custom product direct pay."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    telegram_id = update.effective_user.id
    db_user = context.user_data["db_user"]

    parts = query.data.split(":")
    product_id = int(parts[2])
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = await db.get_custom_product(product_id)
    if not product or not product.get("is_active"):
        await query.edit_message_text(
            "❌ Sản phẩm không tồn tại.",
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    stock = product.get("stock", 0)
    if quantity > stock:
        await query.edit_message_text(
            f"⚠️ Tồn kho không đủ ({stock}). Vui lòng chọn lại.",
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    price = product["price"]
    total = price * quantity

    # Create pending order
    order = await db.create_order(
        user_id=db_user["id"],
        product_id=f"custom_{product_id}",
        product_name=product["name"],
        quantity=quantity,
        original_price=price,
        sell_price=price,
        order_code="",
        delivered_data=[],
        status="pending",
    )

    order_id = order["id"]
    order_code_mem = f"MUA{order_id}"

    # Validate bank config
    if not config.bank_bin or not config.bank_account:
        await query.edit_message_text(
            "⚠️ Admin chưa cấu hình thanh toán ngân hàng. Vui lòng nạp ví trước.",
            reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML",
        )
        return

    # Generate QR
    qr_bytes = await generate_qr_image(total, order_code_mem)
    bank_display = get_bank_display_name(config.bank_bin)

    msg_text = (
        f"🏦 <b>Chuyển khoản tới {bank_display} - {config.bank_account}</b>\n"
        f"👤 Chủ TK: <b>{esc(config.bank_account_name)}</b>\n\n"
        f"💰 Số tiền: <b>{format_vnd(total)}</b>\n"
        f"📝 Nội dung CK: <code>{esc(order_code_mem)}</code>\n"
        f"⏰ Thời gian còn lại: <b>5 phút</b>\n\n"
        f"📱 Quét mã QR bên dưới để chuyển khoản.\n"
        f"⚠️ <b>Lưu ý:</b> Nhập đúng nội dung chuyển khoản!"
    )

    await query.message.delete()
    await context.bot.send_photo(
        chat_id=telegram_id,
        photo=qr_bytes,
        caption=msg_text,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(lang),
    )


def _default_delivery_note() -> str:
    """Fallback delivery note when product has none configured."""
    parts = []
    if config.support_zalo:
        parts.append(f"Zalo https://zalo.me/{config.support_zalo}")
    if config.support_telegram:
        parts.append(f"Telegram https://t.me/{config.support_telegram}")
    contact = " hoặc ".join(parts) if parts else "admin"
    return f"Cung cấp mã đơn hàng cho admin để nhận hàng. Liên hệ qua {contact}"


async def _notify_admin_custom_order(context, user, product, quantity, total, order_id, payment_method):
    """Notify admin about new custom product order."""
    if not config.admin_chat_id:
        return
    try:
        time_str = now_vn().strftime("%H:%M %d/%m/%Y")
        admin_msg = (
            f"🛒 <b>ĐƠN HÀNG CUSTOM MỚI #{order_id}</b>\n\n"
            f"👤 Khách: <b>{esc(user.get('full_name', 'N/A'))}</b> (<code>{user.get('telegram_id', '?')}</code>)\n"
            f"📦 SP: <b>{esc(product['name'])}</b> x{quantity}\n"
            f"💰 Tổng: <b>{format_vnd(total)}</b>\n"
            f"💳 TT: {payment_method}\n\n"
            f"⚠️ <b>Hãy giao hàng cho khách!</b>\n"
            f"⏰ {time_str}"
        )
        await context.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
    except Exception:
        pass

