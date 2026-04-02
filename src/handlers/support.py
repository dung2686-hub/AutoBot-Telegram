import logging

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.keyboards import back_to_menu_keyboard

logger = logging.getLogger(__name__)

WAITING_MESSAGE = 1


@error_handler
@ensure_user
async def support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show support screen — ask user to send a message."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    text = t("support_title", lang)

    await query.edit_message_text(text, parse_mode="HTML")
    return WAITING_MESSAGE


@error_handler
@ensure_user
async def support_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward user's support message to admin."""
    lang = context.user_data.get("lang", "vi")
    user = update.effective_user

    # Notify admin
    admin_text = t("support_admin_notify", lang,
        user=user.full_name or "Unknown",
        username=user.username or "N/A",
        user_id=user.id,
        message=update.message.text,
    )

    try:
        await context.bot.send_message(
            chat_id=config.admin_chat_id,
            text=admin_text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to forward support msg to admin: %s", e)

    await update.message.reply_text(
        t("support_sent", lang),
        reply_markup=back_to_menu_keyboard(lang),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def support_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    return ConversationHandler.END


def get_support_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(support_menu, pattern=r"^menu:support$"),
        ],
        states={
            WAITING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive_message),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(support_cancel, pattern=r"^menu:"),
        ],
        per_message=False,
    )
