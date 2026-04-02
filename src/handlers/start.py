import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)

BOT_NAME = "AI Store Bot"


@error_handler
@ensure_user
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — show welcome + main menu."""
    lang = context.user_data.get("lang", "vi")

    text = t("welcome", lang, bot_name=BOT_NAME)
    keyboard = main_menu_keyboard(lang)

    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


@error_handler
@ensure_user
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback to return to main menu."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    text = t("welcome", lang, bot_name=BOT_NAME)
    keyboard = main_menu_keyboard(lang)

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
