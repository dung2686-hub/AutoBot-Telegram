import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.keyboards import language_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)


@error_handler
@ensure_user
async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language selection."""
    query = update.callback_query
    await query.answer()

    text = t("language_title")
    await query.edit_message_text(text, reply_markup=language_keyboard(), parse_mode="HTML")


@error_handler
@ensure_user
async def language_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set user language preference."""
    query = update.callback_query
    await query.answer()

    db = context.bot_data["db"]
    telegram_id = update.effective_user.id

    parts = query.data.split(":")
    new_lang = parts[1]

    await db.set_user_language(telegram_id, new_lang)
    context.user_data["lang"] = new_lang

    # Refresh db_user cache
    db_user = await db.get_user(telegram_id)
    context.user_data["db_user"] = db_user

    text = t("language_changed", new_lang)
    from src.handlers.start import BOT_NAME
    welcome = t("welcome", new_lang, bot_name=BOT_NAME)

    await query.edit_message_text(
        f"{text}\n\n{welcome}",
        reply_markup=main_menu_keyboard(new_lang),
        parse_mode="HTML",
    )
