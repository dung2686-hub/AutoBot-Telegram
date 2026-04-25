from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

BROADCAST_MESSAGE = 10
CREDIT_INPUT = 11
MARKUP_INPUT = 12
MARKUP_SELECT = 13
NOTE_INPUT = 14
CUSTOM_NAME = 15
CUSTOM_PRICE = 16
CUSTOM_EDIT_PRICE = 17
CUSTOM_EDIT_MENU = 18
CUSTOM_EDIT_NAME = 19
CHECKUSER_INPUT = 20
QUICKCREDIT_INPUT = 21
CUSTOM_EDIT_STOCK = 22
CUSTOM_EDIT_NOTE = 23
CUSTOM_ADD_STOCK = 24
CUSTOM_ADD_NOTE = 25

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END
