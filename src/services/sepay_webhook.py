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
        # Find pending deposit by ID
        deposit_id = int(code_id)
        deposit_row = await _db._fetch_one("SELECT * FROM deposits WHERE id = ? AND status != 'completed'", (deposit_id,))
            
        if not deposit_row:
            logger.warning("SePay webhook: no valid deposit found for NAP %d", deposit_id)
            return web.json_response({"success": True})

        deposit = dict(deposit_row)
        user_row = await _db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (deposit["user_id"],))
        if not user_row: return web.json_response({"success": True})
        
        telegram_id = user_row["telegram_id"]
        
        # WE CREDIT WHATEVER AMOUNT THEY TRANSFERRED
        await _db.complete_deposit(deposit["id"], reference_code)
        new_balance = await _db.update_balance(telegram_id, amount)
        
        await _db.add_transaction(
            user_id=deposit["user_id"], tx_type="deposit", amount=amount,
            balance_after=new_balance, description=f"Nạp tiền (NAP {deposit_id})", reference_id=str(deposit["id"])
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
        logger.info("Deposit completed: NAP %d", deposit_id)

    elif prefix == "MUA":
        order_id = int(code_id)
        order = await _db.get_order(order_id)
        
        if not order or order["status"] == "completed":
            logger.warning("SePay MUA webhook: order %d not found or already completed", order_id)
            return web.json_response({"success": True})

        user_row = await _db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (order["user_id"],))
        telegram_id = user_row["telegram_id"] if user_row else None
        
        from src.utils.formatters import format_vnd
        
        # LATE PAYMENT OR PARTIAL PAYMENT FALLBACK
        if order["status"] != "pending" or amount < order["total_amount"]:
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
                    reason = "giao dịch quá hạn" if order["status"] != "pending" else "thanh toán không đủ số dư"
                    msg = (
                        f"⚠️ <b>Xử lý đơn hàng {order_id} thất bại do {reason}!</b>\n\n"
                        f"Phát hiện khoản thanh toán <b>{format_vnd(amount)}</b>.\n"
                        f"Hệ thống đã tự động gỡ lỗi và cộng số tiền này vào <b>Số dư ví</b> của bạn để không bị thất thoát.\n"
                        f"📌 <i>Số dư hiện tại: {format_vnd(new_balance)}</i>\n\n"
                        f"Bạn có thể dùng ví để mua lại sản phẩm."
                    )
                    await _bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")
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
            if not product or current_cost >= order["sell_price"]:
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
                        f"Đơn: MUA {order_id}\n"
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
                if _bot_app and telegram_id:
                    accounts_text = format_account_list(delivered, lang)
                    msg = t("purchase_success", lang,
                        name=order["product_name"], quantity=order["quantity"],
                        total=format_vnd(order["total_amount"]), 
                        balance=format_vnd(user["balance"] if user else 0), accounts=accounts_text
                    )
                    await _bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")
        except Exception as e:
            logger.error("Failed handling MUA %d: %s", order_id, e)

    return web.json_response({"success": True})


async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/sepay", handle_sepay_webhook)
    app.router.add_get("/health", health_check)
    return app
