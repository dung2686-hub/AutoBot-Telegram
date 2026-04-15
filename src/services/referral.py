import logging
from src.config import config
from src.utils.formatters import format_vnd, esc

logger = logging.getLogger(__name__)

async def process_referral_bonus(db, bot_app, order_id: int, user_id: int, total_amount: float) -> bool:
    """
    Checks and pays referral bonus for a completed order.
    Notifies the referrer and the admin if a bonus was paid out.
    Returns True if a bonus was paid, False otherwise.
    """
    try:
        bonus = await db.check_and_pay_referral_bonus(user_id, total_amount)
        if bonus <= 0:
            return False
            
        # Get user details for notifications
        buyer = await db._fetch_one("SELECT full_name, referred_by FROM users WHERE id = ?", (user_id,))
        if not buyer or not buyer["referred_by"]:
            return True # Edge case: bonus paid but user data missing

        referrer = await db._fetch_one("SELECT telegram_id, full_name FROM users WHERE id = ?", (buyer["referred_by"],))
        
        if not referrer:
            return True
            
        referrer_telegram_id = referrer["telegram_id"]
        referrer_name = esc(referrer["full_name"] or "N/A")
        buyer_name = esc(buyer["full_name"] or "N/A")

        # Notify the referrer
        if bot_app and referrer_telegram_id:
            try:
                msg_ref = (
                    f"🎉 <b>Chúc mừng!</b>\n"
                    f"Người bạn giới thiệu vừa hoàn thành đơn hàng đầu tiên. "
                    f"Bạn được cộng <b>{format_vnd(bonus)}</b> vào ví."
                )
                await bot_app.bot.send_message(chat_id=referrer_telegram_id, text=msg_ref, parse_mode="HTML")
            except Exception as e:
                logger.warning("Failed to notify referrer %s about bonus: %s", referrer_telegram_id, e)

        # Notify the admin
        if bot_app and config.admin_chat_id:
            try:
                admin_ref_msg = (
                    f"🎁 <b>Referral Bonus</b>\n\n"
                    f"👤 Người nhận: <b>{referrer_name}</b>\n"
                    f"👥 Từ khách: <b>{buyer_name}</b> (đơn MUA{order_id})\n"
                    f"💰 Bonus: <b>{format_vnd(bonus)}</b> (10%)\n"
                    f"📦 Đơn: {format_vnd(total_amount)}"
                )
                await bot_app.bot.send_message(chat_id=config.admin_chat_id, text=admin_ref_msg, parse_mode="HTML")
            except Exception as e:
                logger.warning("Failed to notify admin about referral bonus: %s", e)
                
        return True
    except Exception as e:
        logger.error("Error processing referral bonus for user %d: %s", user_id, e)
        return False
