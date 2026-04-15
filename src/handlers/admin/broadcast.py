from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from src.i18n import t
from src.utils.decorators import ensure_user, admin_only, error_handler
from src.utils.keyboards import admin_keyboard
from .states import BROADCAST_MESSAGE

@error_handler
@ensure_user
@admin_only
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(t("admin_broadcast_prompt", "vi"), parse_mode="HTML")
    context.user_data["active_conv"] = "admin_broadcast"
    return BROADCAST_MESSAGE

@error_handler
@ensure_user
@admin_only
async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("active_conv") != "admin_broadcast":
        return ConversationHandler.END

    db = context.bot_data["db"]
    message_text = update.message.text

    user_ids = await db.get_all_user_ids()
    sent = 0

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message_text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass

    await update.message.reply_text(
        t("admin_broadcast_done", "vi", count=sent),
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
    return ConversationHandler.END
