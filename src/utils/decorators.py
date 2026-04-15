import functools
import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.config import config
from src.i18n import t

logger = logging.getLogger(__name__)


def ensure_user(func):
    """Decorator to ensure user exists in DB before handler executes."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        db = context.bot_data["db"]
        user = update.effective_user
        if not user:
            return

        db_user = await db.get_or_create_user(
            telegram_id=user.id,
            username=user.username or "",
            full_name=user.full_name or "",
            lang=config.default_language,
        )
        context.user_data["db_user"] = db_user
        context.user_data["lang"] = db_user.get("language", config.default_language)

        return await func(update, context, *args, **kwargs)
    return wrapper


def admin_only(func):
    """Decorator to restrict handler to admin only."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id not in config.admin_chat_ids:
            lang = context.user_data.get("lang", "vi")
            if update.callback_query:
                await update.callback_query.answer(t("error_not_admin", lang), show_alert=True)
            else:
                await update.effective_message.reply_text(t("error_not_admin", lang))
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def error_handler(func):
    """Decorator for graceful error handling in handlers."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.exception("Handler error in %s: %s", func.__name__, e)
            lang = context.user_data.get("lang", "vi")
            msg = t("error_generic", lang)
            try:
                if update.callback_query:
                    await update.callback_query.answer(msg, show_alert=True)
                elif update.effective_message:
                    await update.effective_message.reply_text(msg)
            except Exception:
                # answer() already called — fallback to send_message
                try:
                    chat_id = update.effective_chat.id if update.effective_chat else None
                    if chat_id:
                        await context.bot.send_message(chat_id=chat_id, text=msg)
                except Exception:
                    pass

            # If inside a ConversationHandler, end the conversation to prevent stuck state
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
    return wrapper

