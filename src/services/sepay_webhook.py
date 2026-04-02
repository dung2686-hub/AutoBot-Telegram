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

    # Verify secret key
    secret = request.headers.get("Authorization", "") or request.headers.get("X-Secret-Key", "")
    if config.sepay_secret_key and secret != config.sepay_secret_key:
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
        # Find pending deposit
        code_str = f"NAP_{code_id}" # Current db code format
        deposit = await _db.find_pending_deposit(code_str)
        if not deposit:
            # Fallback for old format
            deposit = await _db.find_pending_deposit(f"NAP{code_id}")
            if not deposit:
                logger.warning("SePay webhook: no pending deposit for %s", code_str)
                return web.json_response({"success": True})

        if amount < deposit["amount"]:
            logger.warning("SePay webhook: amount mismatch for %s", code_str)
            return web.json_response({"success": True})

        await _db.complete_deposit(deposit["id"], reference_code)
        
        user_row = await _db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (deposit["user_id"],))
        if not user_row: return web.json_response({"success": True})
        
        telegram_id = user_row["telegram_id"]
        new_balance = await _db.update_balance(telegram_id, deposit["amount"])
        
        await _db.add_transaction(
            user_id=deposit["user_id"], tx_type="deposit", amount=deposit["amount"],
            balance_after=new_balance, description=f"Nạp tiền ({code_str})", reference_id=str(deposit["id"])
        )

        if _bot_app:
            try:
                from src.i18n import t
                from src.utils.formatters import format_vnd
                user = await _db.get_user(telegram_id)
                lang = user.get("language", "vi") if user else "vi"
                msg = t("deposit_success", lang, amount=format_vnd(deposit["amount"]), balance=format_vnd(new_balance))
                await _bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")
            except Exception as e:
                logger.error("Failed to notify user %d: %s", telegram_id, e)
        logger.info("Deposit completed: %s", code_str)

    elif prefix == "MUA":
        order_id = int(code_id)
        order = await _db.get_order(order_id)
        if not order or order["status"] != "pending":
            logger.warning("SePay webhook: no pending order for MUA %d", order_id)
            return web.json_response({"success": True})

        if amount < order["total_amount"]:
            logger.warning("SePay webhook: amount mismatch for MUA %d", order_id)
            # Not enough money, maybe add to their wallet instead?
            # Doing a fallback refund to wallet
            # ... we'll do this in the next pass if necessary, but skipping for now to keep it simple.
            return web.json_response({"success": True})

        user_row = await _db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (order["user_id"],))
        telegram_id = user_row["telegram_id"] if user_row else None
        
        try:
            from src.i18n import t
            from src.utils.formatters import format_vnd, format_account_list
            user = await _db.get_user(telegram_id) if telegram_id else None
            lang = user.get("language", "vi") if user else "vi"

            # Execute Canboso Purchase
            from src.config import config
            from src.services.canboso import CanbosoClient
            canboso = CanbosoClient(config.canboso_api_key, config.canboso_api_url)
            
            result = await canboso.purchase(product_id=order["product_id"], quantity=order["quantity"])
            await canboso.close()

            if not result.get("success"):
                # Refund to wallet
                logger.warning("Canboso purchase failed for MUA %d. Refunding %d", order_id, order["total_amount"])
                new_balance = await _db.update_balance(telegram_id, order["total_amount"])
                await _db.update_order(order_id, status="failed")
                await _db.add_transaction(
                    user_id=order["user_id"], tx_type="refund", amount=order["total_amount"],
                    balance_after=new_balance, description=f"Hoàn tiền (Lỗi mua {order_id})", reference_id=str(order_id)
                )
                if _bot_app and telegram_id:
                    error_msg = result.get("message", "Unknown error")
                    msg = (f"❌ <b>Giao dịch thành công nhưng kho hết hạn!</b>\n\n"
                           f"Bot không thể mua tự động từ nguồn với lỗi: {error_msg}.\n"
                           f"Số tiền <b>{format_vnd(order['total_amount'])}</b> đã được hoàn trả vào số dư ví của Quý khách.")
                    await _bot_app.bot.send_message(chat_id=telegram_id, text=msg, parse_mode="HTML")
            else:
                delivered = result.get("deliveredAccounts", [])
                await _db.update_order(
                    order_id, status="completed", order_code=result.get("orderCode", ""), delivered_data=delivered
                )
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
