import json
import logging
import time
from collections import defaultdict

import re
from aiohttp import web
from src.config import config
from src.utils.formatters import format_vnd, now_vn, esc, format_account_list
from src.i18n import t
from src.services.referral import process_referral_bonus
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# ── Rate Limiting ─────────────────────────────────────────
MAX_REQUESTS_PER_MINUTE = 30
MAX_TRANSFER_AMOUNT = 50_000_000  # 50M VND safety cap

class RateLimiter:
    """In-memory rate limiter using sliding window."""
    def __init__(self, max_requests: int = MAX_REQUESTS_PER_MINUTE, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self._store: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        timestamps = self._store[client_ip]
        # Prune old entries
        self._store[client_ip] = [ts for ts in timestamps if now - ts < self.window]
        if len(self._store[client_ip]) >= self.max_requests:
            return True
        self._store[client_ip].append(now)
        return False


# This will be set from main.py
_bot_app = None
_db = None


def set_dependencies(bot_app, db):
    global _bot_app, _db
    _bot_app = bot_app
    _db = db


async def _claim_webhook(db, reference_code: str, prefix: str, code_id: str, amount: int) -> bool:
    """Claim a webhook for processing. Returns True if claimed successfully."""
    if not reference_code:
        return True
    cursor = await db.conn.execute(
        "INSERT OR IGNORE INTO processed_webhooks (reference_code, prefix, code_id, amount, status) "
        "VALUES (?, ?, ?, ?, 'processing')",
        (reference_code, prefix, int(code_id), amount),
    )
    await db.conn.commit()
    if cursor.rowcount == 1:
        return True
    existing = await db.get_processed_webhook(reference_code)
    if not existing:
        return False
    if existing["status"] == "completed":
        logger.info("Duplicate webhook ignored (ref=%s)", reference_code)
        return False
    if existing["status"] == "processing":
        logger.info("Webhook already processing (ref=%s)", reference_code)
        return False
    # status == 'failed' -> reclaim
    reclaim = await db.conn.execute(
        "UPDATE processed_webhooks SET status = 'processing', processed_at = CURRENT_TIMESTAMP "
        "WHERE reference_code = ? AND status = 'failed'", (reference_code,)
    )
    await db.conn.commit()
    return reclaim.rowcount == 1


async def _mark_webhook(db, reference_code: str, status: str):
    """Mark webhook as completed or failed."""
    if not reference_code:
        return
    try:
        await db.conn.execute(
            "UPDATE processed_webhooks SET status = ? WHERE reference_code = ?",
            (status, reference_code),
        )
        await db.conn.commit()
    except Exception:
        logger.warning("Failed to mark webhook %s ref=%s", status, reference_code)


async def handle_sepay_webhook(request: web.Request) -> web.Response:
    """Handle incoming SePay webhook for bank transfer verification."""
    
    db = request.app.get('db')
    bot_app = request.app.get('bot_app')
    rate_limiter = request.app.get('rate_limiter')
    
    if not db or not rate_limiter:
        logger.error("SePay webhook: improperly configured app context")
        return web.json_response({"success": False, "error": "App poorly configured"}, status=500)

    # ── Rate Limiting ──
    client_ip = request.remote or "unknown"
    if rate_limiter.is_rate_limited(client_ip):
        logger.warning("SePay webhook: rate limited IP %s", client_ip)
        return web.json_response({"success": False, "error": "Rate limited"}, status=429)

    # Verify secret key — MANDATORY, reject if key not configured or mismatch
    secret = request.headers.get("Authorization", "") or request.headers.get("X-Secret-Key", "")
    if not config.sepay_secret_key:
        logger.error("SePay webhook: SEPAY_SECRET_KEY not configured! Rejecting all requests.")
        return web.json_response({"success": False, "error": "Webhook key not configured"}, status=500)
    if secret != config.sepay_secret_key:
        logger.warning("SePay webhook: invalid secret key from %s", client_ip)
        return web.json_response({"success": False}, status=401)

    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"success": False}, status=400)

    # ── Sanitized logging (Sec 1) — only log safe fields ──
    transfer_type = data.get("transferType")
    content = data.get("content", "").upper()
    amount = data.get("transferAmount", 0)
    reference_code = data.get("referenceCode", "")
    logger.info(
        "SePay webhook: type=%s amount=%s content=%s ref=%s",
        transfer_type, amount, content, reference_code,
    )

    if transfer_type != "in":
        return web.json_response({"success": True})

    if not amount:
        logger.warning("SePay webhook: missing amount")
        return web.json_response({"success": True})

    # ── Amount bounds validation (Sec 4) ──
    if amount > MAX_TRANSFER_AMOUNT:
        logger.warning("SePay webhook: amount %d exceeds safety cap %d", amount, MAX_TRANSFER_AMOUNT)
        if bot_app and config.admin_chat_id:
            try:
                alert = (
                    f"🚨 <b>CẢNH BÁO: Giao dịch vượt giới hạn!</b>\n\n"
                    f"💰 Số tiền: <b>{format_vnd(amount)}</b>\n"
                    f"📝 Nội dung: <code>{esc(content)}</code>\n"
                    f"🔖 Ref: <code>{esc(reference_code)}</code>\n\n"
                    f"⚠️ Giao dịch bị từ chối tự động. Kiểm tra sao kê ngân hàng."
                )
                for admin_id in config.admin_chat_ids:
                    await bot_app.bot.send_message(chat_id=admin_id, text=alert, parse_mode="HTML")
            except Exception:
                pass
        return web.json_response({"success": True})

    match = re.search(r"(NAP|MUA)[\s_]*(\d+)", content)
    if not match:
        logger.warning("SePay webhook: no matching prefix (NAP/MUA) in content: %s", content)
        return web.json_response({"success": True})

    prefix = match.group(1)
    code_id = match.group(2)

    # -- Idempotency guard --
    claimed = await _claim_webhook(db, reference_code, prefix, code_id, amount)
    if not claimed:
        return web.json_response({"success": True})

    if prefix == "NAP":
        # Find pending deposit by ID (accept 'expired' for late payments)
        deposit_id = int(code_id)
        sender_name = esc(data.get("senderName", "N/A"))

        deposit_row = await db.get_deposit_by_id(deposit_id)

        # Check if deposit exists and is still valid to claim
        if not deposit_row or deposit_row.get("status") not in ("pending", "expired"):
            # If it's already completed, check if we need to alert admin about duplicate
            completed_row = deposit_row if deposit_row and deposit_row.get("status") == "completed" else None
            
            if completed_row and bot_app and config.admin_chat_id:
                try:
                    user_info_str = "Không tìm thấy User"
                    user_row = await db.get_user_by_id(completed_row["user_id"])
                    if user_row:
                        telegram_id = user_row["telegram_id"]
                        user_name = esc(user_row["full_name"] or "N/A")
                        user_info_str = f"<b>{user_name}</b> (<code>{telegram_id}</code>)"

                    time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                    alert_msg = (
                        f"⚠️ <b>CẢNH BÁO: Nạp tiền đúp/trùng mã!</b>\n\n"
                        f"Lệnh <b>NAP{deposit_id}</b> đã hoàn tất trước đó,\n"
                        f"nhưng vừa nhận thêm <b>{format_vnd(amount)}</b>.\n\n"
                        f"👤 Chủ đơn: {user_info_str}\n"
                        f"🏦 Người chuyển: <b>{sender_name}</b>\n"
                        f"📝 Nội dung: <code>{esc(content)}</code>\n"
                        f"🔖 Mã GD: <code>{esc(reference_code)}</code>\n"
                        f"⏰ {time_str}\n\n"
                        f"💡 Dùng lệnh <code>/checkuser {user_row['telegram_id'] if user_row else ''}</code> để xử lý."
                    )
                    await bot_app.bot.send_message(chat_id=config.admin_chat_id, text=alert_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error("Failed to alert admin about duplicate NAP payment: %s", e)
            logger.warning("SePay webhook: no valid deposit found for NAP %d", deposit_id)
            await _mark_webhook(db, reference_code, "completed")
            return web.json_response({"success": True})

        deposit = dict(deposit_row)
        user_row = await db.get_user_by_id(deposit["user_id"])
        if not user_row:
            await _mark_webhook(db, reference_code, "completed")
            return web.json_response({"success": True})
        
        telegram_id = user_row["telegram_id"]
        user_full_name = esc(user_row["full_name"] or "N/A")
        
        # Credit wallet (accept both pending and late payments)
        try:
            await db.complete_deposit(deposit["id"], reference_code)
            new_balance = await db.update_balance(telegram_id, amount)
        
            await db.add_transaction(
                user_id=deposit["user_id"], tx_type="deposit", amount=amount,
                balance_after=new_balance, description=f"Nạp tiền (NAP{deposit_id})", reference_id=str(deposit["id"])
            )

            if bot_app:
                try:
                    user = await db.get_user(telegram_id)
                    lang = user.get("language", "vi") if user else "vi"
                    msg = t("deposit_success", lang, amount=format_vnd(amount), balance=format_vnd(new_balance))
                    if deposit['status'] != 'pending':
                        msg = f"⏱ <b>Khoản nạp trễ được xử lý!</b>\n\n" + msg
                    await bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")
                except Exception as e:
                    logger.error("Failed to notify user %d: %s", telegram_id, e)

            # ADMIN: Notify every deposit with senderName for fraud detection
            if bot_app and config.admin_chat_id:
                try:
                    time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                    late = " ⏱ (trễ)" if deposit['status'] != 'pending' else ""
                    admin_msg = (
                        f"💰 <b>NẠP VÍ NAP{deposit_id}{late}</b>\n\n"
                        f"👤 User: <b>{user_full_name}</b> (<code>{telegram_id}</code>)\n"
                        f"🏦 Người chuyển: <b>{sender_name}</b>\n"
                        f"💵 Số tiền: <b>{format_vnd(amount)}</b>\n"
                        f"📊 Số dư mới: {format_vnd(new_balance)}\n"
                        f"⏰ {time_str}"
                    )
                    await bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
                except Exception:
                    pass
            logger.info("Deposit completed: NAP %d (sender: %s)", deposit_id, sender_name)
        except Exception as e:
            logger.exception("Failed handling NAP %d: %s", deposit_id, e)
            await _mark_webhook(db, reference_code, "failed")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif prefix == "MUA":
        order_id = int(code_id)
        order = await db.get_order(order_id)
        
        if not order:
            logger.warning("SePay MUA webhook: order %d not found", order_id)
            await _mark_webhook(db, reference_code, "completed")
            return web.json_response({"success": True})

        if order["status"] == "completed":
            logger.warning("SePay MUA webhook: order %d already completed, duplicate payment of %d", order_id, amount)
            if bot_app and config.admin_chat_id:
                try:
                    sender_name = esc(data.get("senderName", "N/A"))
                    time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                    alert_msg = (
                        f"⚠️ <b>CẢNH BÁO: Thanh toán trùng!</b>\n\n"
                        f"Đơn <b>MUA{order_id}</b> đã hoàn tất trước đó,\n"
                        f"nhưng vừa nhận thêm <b>{format_vnd(amount)}</b>.\n\n"
                        f"👤 Người chuyển: <b>{sender_name}</b>\n"
                        f"📝 Nội dung: <code>{esc(content)}</code>\n"
                        f"🔖 Mã GD: <code>{esc(reference_code)}</code>\n"
                        f"⏰ {time_str}\n\n"
                        f"💡 Tiền đã vào bank. Kiểm tra sao kê để xử lý."
                    )
                    await bot_app.bot.send_message(chat_id=config.admin_chat_id, text=alert_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error("Failed to alert admin about duplicate MUA payment: %s", e)
            await _mark_webhook(db, reference_code, "completed")
            return web.json_response({"success": True})

        user_row = await db.get_user_by_id(order["user_id"])
        telegram_id = user_row["telegram_id"] if user_row else None
        
        
        
        # LATE PAYMENT, PARTIAL PAYMENT, or EXPIRED ORDER FALLBACK
        is_expired = order["status"] not in ("pending",)
        is_underpaid = amount < order["total_amount"]
        
        if is_expired or is_underpaid:
            logger.warning("SePay MUA Fallback: Order %d (Status: %s, Paid: %d, Need: %d)", order_id, order["status"], amount, order["total_amount"])
            if telegram_id:
                new_balance = await db.update_balance(telegram_id, amount)
                # Don't update order status here since it could be failed/expired already, or we fail it now if insufficient
                if order["status"] == "pending":
                    await db.update_order(order_id, status="failed")
                    
                await db.add_transaction(
                    user_id=order["user_id"], tx_type="refund", amount=amount,
                    balance_after=new_balance, description=f"Hoàn tiền QR ({order_id})", reference_id=str(order_id)
                )
                if bot_app:
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
                    await bot_app.bot.send_message(
                        chat_id=telegram_id, text=msg,
                        reply_markup=kb, parse_mode="HTML"
                    )
            await _mark_webhook(db, reference_code, "completed")
            return web.json_response({"success": True})

        user_row = await db.get_user_by_id(order["user_id"])
        telegram_id = user_row["telegram_id"] if user_row else None
        
        try:
            user = await db.get_user(telegram_id) if telegram_id else None
            lang = user.get("language", "vi") if user else "vi"

            # Reuse shared CanbosoClient from bot_data
            canboso = bot_app.bot_data["canboso"]
            
            # --- PROTECT AGAINST PRICE SLIPPAGE ---
            await canboso.refresh_cache()
            product = canboso.find_product(order["product_id"])
            current_cost = product.get("walletPricing", 0) if product else float('inf')
            
            # If the product cost is now higher than what we sold it for, abort!
            if not product or current_cost > order["sell_price"]:
                logger.warning(f"Slippage detected! Order {order_id}. New Canboso Cost: {current_cost}, Customer Paid: {order['sell_price']}")
                result = {"success": False, "message": "Sản phẩm đổi giá hoặc ngừng bán từ hệ thống tổng"}
            else:
                result = await canboso.purchase(product_id=order["product_id"], quantity=order["quantity"])

            if not result.get("success"):
                # Refund to wallet
                error_msg = result.get("message", "Unknown error")
                logger.warning("Canboso purchase failed for MUA %d. Refunding %d. Reason: %s", order_id, order["total_amount"], error_msg)
                new_balance = await db.update_balance(telegram_id, order["total_amount"])
                await db.update_order(order_id, status="failed")
                await db.add_transaction(
                    user_id=order["user_id"], tx_type="refund", amount=order["total_amount"],
                    balance_after=new_balance, description=f"Hoàn tiền (Lỗi mua {order_id})", reference_id=str(order_id)
                )
                if bot_app and telegram_id:
                    msg = (f"❌ <b>Giao dịch thành công nhưng kho hết hạn!</b>\n\n"
                           f"Bot không thể mua tự động từ nguồn với lỗi: {error_msg}.\n"
                           f"Số tiền <b>{format_vnd(order['total_amount'])}</b> đã được hoàn trả vào số dư ví của Quý khách.")
                    await bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")

                # === PATCH C: ALERT ADMIN ===
                if bot_app and config.admin_chat_id:
                    user_name = esc(user.get("full_name", "N/A")) if user else "N/A"
                    user_tid = telegram_id or "?"
                    admin_msg = (
                        f"🚨 <b>CẢNH BÁO: Mua sỉ thất bại!</b>\n\n"
                        f"👤 Khách: <b>{user_name}</b> (<code>{user_tid}</code>)\n"
                        f"Đơn: MUA{order_id}\n"
                        f"Sản phẩm: {esc(order['product_name'])}\n"
                        f"SL: {order['quantity']}\n"
                        f"Lỗi: <code>{esc(error_msg)}</code>\n\n"
                        f"Đã hoàn {format_vnd(order['total_amount'])} vào ví khách.\n"
                        f"⚠️ Kiểm tra số dư Canboso ngay!"
                    )
                    try:
                        await bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
                    except Exception as admin_err:
                        logger.error("Failed to alert admin: %s", admin_err)
            else:
                delivered = result.get("deliveredAccounts", [])
                await db.update_order(
                    order_id, status="completed", order_code=result.get("orderCode", ""), delivered_data=delivered
                )
                # Referral bonus disabled — uncomment to re-enable
                # await process_referral_bonus(db, bot_app, order_id, order["user_id"], order["total_amount"])
                if bot_app and telegram_id:
                    accounts_text = format_account_list(delivered, lang)
                    msg = t("purchase_success", lang,
                        name=esc(order["product_name"]), quantity=order["quantity"],
                        total=format_vnd(order["total_amount"]), accounts=accounts_text
                    )
                    await bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")

                # === NOTIFY ADMIN: New order completed ===
                if bot_app and config.admin_chat_id:
                    try:
                        cost = order["original_price"] * order["quantity"]
                        profit = order["total_amount"] - cost
                        time_str = now_vn().strftime("%H:%M %d/%m/%Y")
                        admin_msg = (
                            f"🛒 <b>ĐƠN HÀNG MỚI #{order_id}</b>\n\n"
                            f"👤 Khách: {esc(user.get('full_name', 'N/A') if user else 'N/A')}\n"
                            f"📦 SP: {esc(order['product_name'])} x{order['quantity']}\n"
                            f"💰 Bán: {format_vnd(order['total_amount'])}\n"
                            f"💵 Vốn: {format_vnd(cost)}\n"
                            f"📊 Lãi: +{format_vnd(profit)}\n"
                            f"💳 TT: QR chuyển khoản\n\n"
                            f"⏰ {time_str}"
                        )
                        await bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_msg, parse_mode="HTML")
                    except Exception:
                        pass
        except Exception as e:
            logger.exception("Failed handling MUA %d: %s", order_id, e)
            await _mark_webhook(db, reference_code, "failed")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    await _mark_webhook(db, reference_code, "completed")
    return web.json_response({"success": True})


async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_webhook_app(bot_app=None, db=None) -> web.Application:
    app = web.Application()
    app['bot_app'] = bot_app
    app['db'] = db
    app['rate_limiter'] = RateLimiter(max_requests=MAX_REQUESTS_PER_MINUTE, window=60)
    app.router.add_post("/webhook/sepay", handle_sepay_webhook)
    app.router.add_get("/health", health_check)
    return app
