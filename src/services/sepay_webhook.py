import json
import logging

from aiohttp import web

from src.config import config

logger = logging.getLogger(__name__)

# This will be set from main.py
_bot_app = None
_db = None


def set_dependencies(bot_app, db):
    global _bot_app, _db
    _bot_app = bot_app
    _db = db


async def handle_sepay_webhook(request: web.Request) -> web.Response:
    """Handle incoming SePay webhook for bank transfer verification."""

    # Verify secret key — MANDATORY, reject if key not configured or mismatch
    secret = request.headers.get("Authorization", "") or request.headers.get("X-Secret-Key", "")
    if not config.sepay_secret_key:
        logger.error("SePay webhook: SEPAY_SECRET_KEY not configured! Rejecting all requests.")
        return web.json_response({"success": False, "error": "Webhook key not configured"}, status=500)
    if secret != config.sepay_secret_key:
        logger.warning("SePay webhook: invalid secret key")
        return web.json_response({"success": False}, status=401)

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"success": False}, status=400)

    logger.info("SePay webhook received: %s", json.dumps(data, ensure_ascii=False))

    transfer_type = data.get("transferType")
    if transfer_type != "in":
        # Ignore outgoing transfers
        return web.json_response({"success": True})

    content = data.get("content", "").upper()
    amount = data.get("transferAmount", 0)
    reference_code = data.get("referenceCode", "")

    if not amount:
        logger.warning("SePay webhook: missing amount")
        return web.json_response({"success": True})

    import re
    match = re.search(r"(NAP|MUA)[\s_]*(\d+)", content)
    if not match:
        logger.warning("SePay webhook: no matching prefix (NAP/MUA) in content: %s", content)
        return web.json_response({"success": True})

    prefix = match.group(1)
    code_id = match.group(2)
    
    if prefix == "NAP":
        # Find pending deposit by ID (accept 'expired' for late payments)
        deposit_id = int(code_id)
        sender_name = data.get("senderName", "N/A")

        deposit_row = await _db._fetch_one(
            "SELECT * FROM deposits WHERE id = ? AND status IN ('pending', 'expired')",
            (deposit_id,)
        )
            
        if not deposit_row:
            # Check if it's a duplicate payment for already-completed deposit
            completed_row = await _db._fetch_one(
                "SELECT * FROM deposits WHERE id = ? AND status = 'completed'",
                (deposit_id,)
            )
            if completed_row and _bot_app and config.admin_chat_id:
                try:
                    from src.utils.formatters import format_vnd, now_vn
                    time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                    alert_msg = (
                        f"⚠️ <b>CẢNH BÁO: Nạp tiền trùng!</b>\n\n"
                        f"Lệnh <b>NAP{deposit_id}</b> đã hoàn tất trước đó,\n"
                        f"nhưng vừa nhận thêm <b>{format_vnd(amount)}</b>.\n\n"
                        f"🏦 Người chuyển: <b>{sender_name}</b>\n"
                        f"📝 Nội dung: <code>{content}</code>\n"
                        f"🔖 Mã GD: <code>{reference_code}</code>\n"
                        f"⏰ {time_str}\n\n"
                        f"💡 Tiền đã vào bank. Kiểm tra sao kê để xử lý."
                    )
                    await _bot_app.bot.send_message(chat_id=config.admin_chat_id, text=alert_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error("Failed to alert admin about duplicate NAP payment: %s", e)
            logger.warning("SePay webhook: no valid deposit found for NAP %d", deposit_id)
            return web.json_response({"success": True})

        deposit = dict(deposit_row)
        user_row = await _db._fetch_one("SELECT telegram_id, full_name FROM users WHERE id = ?", (deposit["user_id"],))
        if not user_row: return web.json_response({"success": True})
        
        telegram_id = user_row["telegram_id"]
        user_full_name = user_row["full_name"] or "N/A"
        
        # Credit wallet (accept both pending and late payments)
        await _db.complete_deposit(deposit["id"], reference_code)
        new_balance = await _db.update_balance(telegram_id, amount)
        
        await _db.add_transaction(
            user_id=deposit["user_id"], tx_type="deposit", amount=amount,
            balance_after=new_balance, description=f"Nạp tiền (NAP{deposit_id})", reference_id=str(deposit["id"])
        )

        if _bot_app:
            try:
                from src.i18n import t
                from src.utils.formatters import format_vnd
                user = await _db.get_user(telegram_id)
                lang = user.get("language", "vi") if user else "vi"
                msg = t("deposit_success", lang, amount=format_vnd(amount), balance=format_vnd(new_balance))
                if deposit['status'] != 'pending':
                    msg = f"⏱ <b>Khoản nạp trễ được xử lý!</b>\n\n" + msg
                await _bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")
            except Exception as e:
                logger.error("Failed to notify user %d: %s", telegram_id, e)

        # ADMIN: Notify every deposit with senderName for fraud detection
        if _bot_app and config.admin_chat_id:
            try:
                from src.utils.formatters import format_vnd, now_vn
                time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                name_mismatch = sender_name.upper().strip() not in user_full_name.upper().strip() and user_full_name.upper().strip() not in sender_name.upper().strip()
                warning = "\n\n⚠️ <b>TÊN KHÔNG KHỚP!</b> Người chuyển khác chủ đơn." if name_mismatch else ""
                late = " ⏱ (trễ)" if deposit['status'] != 'pending' else ""
                admin_msg = (
                    f"💰 <b>NẠP VÍ NAP{deposit_id}{late}</b>\n\n"
                    f"👤 User: <b>{user_full_name}</b> (<code>{telegram_id}</code>)\n"
                    f"🏦 Người chuyển: <b>{sender_name}</b>\n"
                    f"💵 Số tiền: <b>{format_vnd(amount)}</b>\n"
                    f"📊 Số dư mới: {format_vnd(new_balance)}\n"
                    f"⏰ {time_str}{warning}"
                )
                await _bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
            except Exception:
                pass
        logger.info("Deposit completed: NAP %d (sender: %s)", deposit_id, sender_name)

    elif prefix == "MUA":
        order_id = int(code_id)
        order = await _db.get_order(order_id)
        
        if not order:
            logger.warning("SePay MUA webhook: order %d not found", order_id)
            return web.json_response({"success": True})

        if order["status"] == "completed":
            logger.warning("SePay MUA webhook: order %d already completed, duplicate payment of %d", order_id, amount)
            if _bot_app and config.admin_chat_id:
                try:
                    from src.utils.formatters import format_vnd, now_vn
                    sender_name = data.get("senderName", "N/A")
                    time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                    alert_msg = (
                        f"⚠️ <b>CẢNH BÁO: Thanh toán trùng!</b>\n\n"
                        f"Đơn <b>MUA{order_id}</b> đã hoàn tất trước đó,\n"
                        f"nhưng vừa nhận thêm <b>{format_vnd(amount)}</b>.\n\n"
                        f"👤 Người chuyển: <b>{sender_name}</b>\n"
                        f"📝 Nội dung: <code>{content}</code>\n"
                        f"🔖 Mã GD: <code>{reference_code}</code>\n"
                        f"⏰ {time_str}\n\n"
                        f"💡 Tiền đã vào bank. Kiểm tra sao kê để xử lý."
                    )
                    await _bot_app.bot.send_message(chat_id=config.admin_chat_id, text=alert_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error("Failed to alert admin about duplicate MUA payment: %s", e)
            return web.json_response({"success": True})

        user_row = await _db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (order["user_id"],))
        telegram_id = user_row["telegram_id"] if user_row else None
        
        from src.utils.formatters import format_vnd
        
        # LATE PAYMENT, PARTIAL PAYMENT, or EXPIRED ORDER FALLBACK
        is_expired = order["status"] not in ("pending",)
        is_underpaid = amount < order["total_amount"]
        
        if is_expired or is_underpaid:
            logger.warning("SePay MUA Fallback: Order %d (Status: %s, Paid: %d, Need: %d)", order_id, order["status"], amount, order["total_amount"])
            if telegram_id:
                new_balance = await _db.update_balance(telegram_id, amount)
                # Don't update order status here since it could be failed/expired already, or we fail it now if insufficient
                if order["status"] == "pending":
                    await _db.update_order(order_id, status="failed")
                    
                await _db.add_transaction(
                    user_id=order["user_id"], tx_type="refund", amount=amount,
                    balance_after=new_balance, description=f"Hoàn tiền QR ({order_id})", reference_id=str(order_id)
                )
                if _bot_app:
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    if order["status"] != "pending":
                        reason_text = "đã hết hạn"
                        reason_emoji = "⏱"
                    else:
                        reason_text = "thanh toán không đủ"
                        reason_emoji = "💸"
                    product_name = order.get('product_name', 'Sản phẩm')
                    msg = (
                        f"{reason_emoji} <b>Nhận được {format_vnd(amount)} cho đơn MUA{order_id}!</b>\n\n"
                        f"📦 Sản phẩm: <b>{product_name}</b>\n"
                        f"💰 Giá đơn: <b>{format_vnd(order['total_amount'])}</b>\n"
                        f"💳 Đã chuyển: <b>{format_vnd(amount)}</b>\n\n"
                        f"Đơn hàng {reason_text} nên không thể xử lý tự động.\n"
                        f"Số tiền đã được <b>hoàn vào Số dư ví</b> để bạn không bị mất.\n\n"
                        f"📌 <i>Số dư hiện tại: {format_vnd(new_balance)}</i>"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛒 Mua lại sản phẩm", callback_data=f"shop:detail:{order['product_id']}")],
                        [InlineKeyboardButton("💳 Xem ví", callback_data="menu:wallet")]
                    ])
                    await _bot_app.bot.send_message(
                        chat_id=telegram_id, text=msg,
                        reply_markup=kb, parse_mode="HTML"
                    )
            return web.json_response({"success": True})

        user_row = await _db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (order["user_id"],))
        telegram_id = user_row["telegram_id"] if user_row else None
        
        try:
            from src.i18n import t
            from src.utils.formatters import format_vnd, format_account_list
            user = await _db.get_user(telegram_id) if telegram_id else None
            lang = user.get("language", "vi") if user else "vi"

            # Execute Canboso Purchase
            from src.services.canboso import CanbosoClient
            canboso = CanbosoClient()
            await canboso.start()
            
            # --- PROTECT AGAINST PRICE SLIPPAGE ---
            await canboso.refresh_cache()
            product = canboso.find_product(order["product_id"])
            current_cost = product.get("walletPricing", 0) if product else float('inf')
            
            # If the product cost is now higher than what we sold it for, abort!
            if not product or current_cost > order["sell_price"]:
                logger.warning(f"Slippage detected! Order {order_id}. New Canboso Cost: {current_cost}, Customer Paid: {order['sell_price']}")
                await canboso.close()
                result = {"success": False, "message": "Sản phẩm đổi giá hoặc ngừng bán từ hệ thống tổng"}
            else:
                result = await canboso.purchase(product_id=order["product_id"], quantity=order["quantity"])
                await canboso.close()

            if not result.get("success"):
                # Refund to wallet
                error_msg = result.get("message", "Unknown error")
                logger.warning("Canboso purchase failed for MUA %d. Refunding %d. Reason: %s", order_id, order["total_amount"], error_msg)
                new_balance = await _db.update_balance(telegram_id, order["total_amount"])
                await _db.update_order(order_id, status="failed")
                await _db.add_transaction(
                    user_id=order["user_id"], tx_type="refund", amount=order["total_amount"],
                    balance_after=new_balance, description=f"Hoàn tiền (Lỗi mua {order_id})", reference_id=str(order_id)
                )
                if _bot_app and telegram_id:
                    msg = (f"❌ <b>Giao dịch thành công nhưng kho hết hạn!</b>\n\n"
                           f"Bot không thể mua tự động từ nguồn với lỗi: {error_msg}.\n"
                           f"Số tiền <b>{format_vnd(order['total_amount'])}</b> đã được hoàn trả vào số dư ví của Quý khách.")
                    await _bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")

                # === PATCH C: ALERT ADMIN ===
                if _bot_app and config.admin_chat_id:
                    admin_msg = (
                        f"🚨 <b>CẢNH BÁO: Mua sỉ thất bại!</b>\n\n"
                        f"Đơn: MUA{order_id}\n"
                        f"Sản phẩm: {order['product_name']}\n"
                        f"SL: {order['quantity']}\n"
                        f"Lỗi: <code>{error_msg}</code>\n\n"
                        f"Đã hoàn {format_vnd(order['total_amount'])} vào ví khách.\n"
                        f"⚠️ Kiểm tra số dư Canboso ngay!"
                    )
                    try:
                        await _bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
                    except Exception as admin_err:
                        logger.error("Failed to alert admin: %s", admin_err)
            else:
                delivered = result.get("deliveredAccounts", [])
                await _db.update_order(
                    order_id, status="completed", order_code=result.get("orderCode", ""), delivered_data=delivered
                )
                # Check and pay referral bonus
                bonus = await _db.check_and_pay_referral_bonus(order["user_id"], order["total_amount"])
                if bonus > 0 and _bot_app:
                    referrer = await _db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (user["referred_by"],))
                    if referrer and referrer["telegram_id"]:
                        try:
                            msg_ref = f"🎉 <b>Chúc mừng!</b>\nNgười bạn giới thiệu vừa hoàn thành đơn hàng đầu tiên. Bạn được cộng <b>{format_vnd(bonus)}</b> vào ví."
                            await _bot_app.bot.send_message(chat_id=referrer["telegram_id"], text=msg_ref, parse_mode="HTML")
                        except Exception:
                            pass
                    # Notify admin about referral bonus
                    if config.admin_chat_id:
                        try:
                            referrer_name = (await _db.get_user(referrer["telegram_id"])).get("full_name", "N/A") if referrer else "N/A"
                            buyer_name = user.get("full_name", "N/A") if user else "N/A"
                            admin_ref_msg = (
                                f"🎁 <b>Referral Bonus</b>\n\n"
                                f"👤 Người nhận: <b>{referrer_name}</b>\n"
                                f"👥 Từ khách: <b>{buyer_name}</b> (đơn MUA{order_id})\n"
                                f"💰 Bonus: <b>{format_vnd(bonus)}</b> (10%)\n"
                                f"📦 Đơn: {format_vnd(order['total_amount'])}"
                            )
                            await _bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_ref_msg, parse_mode="HTML")
                        except Exception:
                            pass
                if _bot_app and telegram_id:
                    accounts_text = format_account_list(delivered, lang)
                    msg = t("purchase_success", lang,
                        name=order["product_name"], quantity=order["quantity"],
                        total=format_vnd(order["total_amount"]), accounts=accounts_text
                    )
                    await _bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")

                # === NOTIFY ADMIN: New order completed ===
                if _bot_app and config.admin_chat_id:
                    try:
                        from src.utils.formatters import now_vn
                        cost = order["original_price"] * order["quantity"]
                        profit = order["total_amount"] - cost
                        time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                        admin_msg = (
                            f"🛒 <b>ĐƠN HÀNG MỚI #{order_id}</b>\n\n"
                            f"👤 Khách: {user.get('full_name', 'N/A') if user else 'N/A'}\n"
                            f"📦 SP: {order['product_name']} x{order['quantity']}\n"
                            f"💰 Bán: {format_vnd(order['total_amount'])}\n"
                            f"💵 Vốn: {format_vnd(cost)}\n"
                            f"📊 Lãi: +{format_vnd(profit)}\n"
                            f"💳 TT: QR chuyển khoản\n\n"
                            f"⏰ {time_str}"
                        )
                        await _bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
                    except Exception:
                        pass
        except Exception as e:
            logger.exception("Failed handling MUA %d: %s", order_id, e)
            # Return 500 so SePay will retry
            return web.json_response({"success": False, "error": str(e)}, status=500)

    return web.json_response({"success": True})


async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/sepay", handle_sepay_webhook)
    app.router.add_get("/health", health_check)
    return app
