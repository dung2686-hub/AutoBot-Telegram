import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.formatters import format_vnd
from src.utils.keyboards import product_detail_keyboard, back_to_menu_keyboard, confirm_cancel_keyboard

logger = logging.getLogger(__name__)


async def calc_sell_price(db, product_id: str, cost_price: int) -> int:
    """Calculate sell price from markup settings. Guarantees min 10k or 20% profit."""
    m = await db.get_markup(product_id, config.default_markup_percent)
    markup_price = int(cost_price * (1 + m["markup_percent"] / 100))
    
    # Đảm bảo lãi tối thiểu 10k HOẶC 20%, tùy cái nào lớn hơn
    min_sell = max(cost_price + 10000, int(cost_price * 1.20))
    markup_price = max(markup_price, min_sell)
    
    if m["fixed_price"] > 0:
        return max(m["fixed_price"], min_sell)
    return markup_price


@error_handler
@ensure_user
async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product listing."""
    query = update.callback_query
    await query.answer()

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
                f"{name} — {format_vnd(sell_price)}{stock_text}",
                callback_data=f"shop:detail:{product_id}",
            )
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
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    # Always refresh to get latest stock
    await canboso.refresh_cache()
    product = canboso.find_product(product_id)

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

    text = t("product_detail", lang,
        name=product.get("product_name", ""),
        description=product.get("description", ""),
        price=format_vnd(sell_price),
        slot_info=slot_info,
        quantity=quantity,
    )

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

    # Stock check
    available = product.get("stats", {}).get("available")
    if available is not None and quantity > available:
        await query.edit_message_text(
            f"⚠️ Số lượng yêu cầu vượt quá tồn kho ({available}). Vui lòng chọn lại.",
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    sell_price = await calc_sell_price(db, product_id, product.get("walletPricing", 0))
    total = sell_price * quantity
    balance = db_user["balance"]

    text = t("confirm_purchase", lang,
        name=product.get("product_name", ""),
        quantity=quantity,
        price=format_vnd(sell_price),
        total=format_vnd(total),
        balance=format_vnd(balance),
    )

    from src.utils.keyboards import payment_options_keyboard
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
    order_code_mem = f"MUA {order_id}"

    # Validate bank config
    from src.services.vietqr import generate_qr_image, get_bank_display_name

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
        f"👤 Chủ TK: <b>{config.bank_account_name}</b>\n\n"
        f"💰 Số tiền: <b>{format_vnd(total)}</b>\n"
        f"📝 Nội dung CK: <code>{order_code_mem}</code>\n"
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
    result = await canboso.purchase(
        product_id=product_id,
        quantity=quantity,
    )

    if not result.get("success"):
        error_msg = result.get("message", "Unknown error")
        await query.edit_message_text(
            t("purchase_error", lang, error=error_msg),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # Deduct balance
    logger.info("[WALLET-PURCHASE] Deducting %s from user %s", total, telegram_id)
    new_balance = await db.update_balance(telegram_id, -total)

    # Get delivered accounts
    delivered = result.get("deliveredAccounts", [])

    # Save order
    user = await db.get_user(telegram_id)
    await db.create_order(
        user_id=user["id"],
        order_code=result.get("orderCode", ""),
        product_id=product_id,
        product_name=product.get("product_name", ""),
        quantity=quantity,
        original_price=product.get("walletPricing", 0),
        sell_price=sell_price,
        delivered_data=delivered,
    )

    # Log transaction
    await db.add_transaction(
        user_id=user["id"],
        tx_type="purchase",
        amount=-total,
        balance_after=new_balance,
        description=f"Mua {product.get('product_name', '')} x{quantity}",
    )

    # Check and pay referral bonus
    try:
        bonus = await db.check_and_pay_referral_bonus(user["id"], total)
        if bonus > 0:
            referrer = await db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (user["referred_by"],))
            if referrer and referrer["telegram_id"]:
                from src.utils.formatters import format_vnd as _fv
                msg_ref = f"🎉 <b>Chúc mừng!</b>\nNgười bạn giới thiệu vừa hoàn thành đơn hàng đầu tiên. Bạn được cộng <b>{_fv(bonus)}</b> vào ví."
                await context.bot.send_message(chat_id=referrer["telegram_id"], text=msg_ref, parse_mode="HTML")
    except Exception as ref_err:
        logger.warning("Referral bonus error (non-critical): %s", ref_err)

    # === SEND RESULT — use send_message (same as QR flow which works) ===
    from src.utils.formatters import format_account_list
    accounts_text = format_account_list(delivered, lang)

    text = t("purchase_success", lang,
        name=product.get("product_name", ""),
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
