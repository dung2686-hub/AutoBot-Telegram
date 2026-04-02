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

    code = data.get("code", "")
    amount = data.get("transferAmount", 0)
    reference_code = data.get("referenceCode", "")

    if not code or not amount:
        logger.warning("SePay webhook: missing code or amount")
        return web.json_response({"success": True})

    # Find pending deposit
    deposit = await _db.find_pending_deposit(code)
    if not deposit:
        logger.warning("SePay webhook: no pending deposit for code %s", code)
        return web.json_response({"success": True})

    # Verify amount matches
    if amount < deposit["amount"]:
        logger.warning(
            "SePay webhook: amount mismatch for %s (expected %d, got %d)",
            code, deposit["amount"], amount,
        )
        return web.json_response({"success": True})

    # Complete deposit
    await _db.complete_deposit(deposit["id"], reference_code)

    # Credit user wallet
    # Find user by user_id from deposit
    user_row = await _db._fetch_one(
        "SELECT telegram_id FROM users WHERE id = ?", (deposit["user_id"],)
    )
    if not user_row:
        logger.error("SePay webhook: user not found for deposit %d", deposit["id"])
        return web.json_response({"success": True})

    telegram_id = user_row["telegram_id"]
    new_balance = await _db.update_balance(telegram_id, deposit["amount"])

    # Log transaction
    await _db.add_transaction(
        user_id=deposit["user_id"],
        tx_type="deposit",
        amount=deposit["amount"],
        balance_after=new_balance,
        description=f"Nạp tiền ({code})",
        reference_id=str(deposit["id"]),
    )

    # Notify user via bot
    if _bot_app:
        try:
            from src.i18n import t
            from src.utils.formatters import format_vnd

            user = await _db.get_user(telegram_id)
            lang = user.get("language", "vi") if user else "vi"

            msg = t("deposit_success", lang,
                amount=format_vnd(deposit["amount"]),
                balance=format_vnd(new_balance),
            )
            await _bot_app.bot.send_message(
                chat_id=telegram_id,
                text=msg,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Failed to notify user %d: %s", telegram_id, e)

    logger.info("Deposit completed: user=%d, amount=%d, code=%s", telegram_id, deposit["amount"], code)
    return web.json_response({"success": True})


async def health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/sepay", handle_sepay_webhook)
    app.router.add_get("/health", health_check)
    return app
