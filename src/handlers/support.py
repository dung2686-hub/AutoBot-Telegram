import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
from src.utils.formatters import esc
from src.utils.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)

INFO_PAGE = 0
WAITING_MESSAGE = 1


def _support_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Build support keyboard with contact URL buttons."""
    buttons = []

    if config.support_zalo:
        buttons.append([InlineKeyboardButton(
            "📞 Zalo Admin", url=f"https://zalo.me/{config.support_zalo}"
        )])

    if config.support_zalo_group:
        url = config.support_zalo_group
        if not url.startswith("http"):
            url = f"https://{url}"
        buttons.append([InlineKeyboardButton(
            "💬 Nhóm Zalo", url=url
        )])

    if config.support_telegram:
        buttons.append([InlineKeyboardButton(
            "✈️ Telegram Admin", url=f"https://t.me/{config.support_telegram}"
        )])

    buttons.append([InlineKeyboardButton(
        t("support_btn_send", lang), callback_data="support:send_msg"
    )])

    buttons.append([
        InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main"),
        InlineKeyboardButton(t("btn_shop", lang), callback_data="menu:shop"),
    ])

    return InlineKeyboardMarkup(buttons)


def _support_text(lang: str) -> str:
    """Build professional support info text."""
    lines = [t("support_header", lang), ""]
    lines.append(f"🏢 {t('support_contact_label', lang)}:")
    lines.append(f"Shop Name: <b>{esc(config.shop_name)}</b>")
    lines.append("")

    if config.support_zalo:
        lines.append(f"📞 Zalo: https://zalo.me/{config.support_zalo}")
    if config.support_zalo_group:
        url = config.support_zalo_group
        if not url.startswith("http"):
            url = f"https://{url}"
        lines.append(f'💬 Box Zalo: <a href="{url}">Tham gia nhóm Zalo</a>')
    if config.support_telegram:
        lines.append(f"🤖 Telegram: @{config.support_telegram}")

    lines.append("")
    lines.append(t("support_cta", lang))
    return "\n".join(lines)


@error_handler
@ensure_user
async def support_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show professional support info page with contact channels."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    await query.edit_message_text(
        _support_text(lang),
        reply_markup=_support_keyboard(lang),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return INFO_PAGE


@error_handler
@ensure_user
async def support_ask_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user to type their support message."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Quay lại Hỗ trợ", callback_data="menu:support")],
        [InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")],
    ])
    await query.edit_message_text(
        t("support_ask_msg", lang), reply_markup=kb, parse_mode="HTML"
    )
    context.user_data["active_conv"] = "support"
    return WAITING_MESSAGE


@error_handler
@ensure_user
async def support_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward user's support message to admin."""
    if context.user_data.get("active_conv") != "support":
        return ConversationHandler.END

    lang = context.user_data.get("lang", "vi")
    user = update.effective_user

    admin_text = t("support_admin_notify", lang,
        user=esc(user.full_name or "Unknown"),
        username=user.username or "N/A",
        user_id=user.id,
        message=esc(update.message.text),
    )

    try:
        await context.bot.send_message(
            chat_id=config.admin_chat_id,
            text=admin_text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to forward support msg to admin: %s", e)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Quay lại Hỗ trợ", callback_data="menu:support")],
        [InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")],
    ])
    await update.message.reply_text(
        t("support_sent", lang), reply_markup=kb, parse_mode="HTML"
    )
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


async def support_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End conversation, let group-0 handlers manage navigation."""
    context.user_data.pop("active_conv", None)
    return ConversationHandler.END


def get_support_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(support_info, pattern=r"^menu:support$"),
        ],
        states={
            INFO_PAGE: [
                CallbackQueryHandler(support_ask_message, pattern=r"^support:send_msg$"),
            ],
            WAITING_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive_message),
                CallbackQueryHandler(support_info, pattern=r"^menu:support$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(support_cancel, pattern=r"^menu:"),
            CallbackQueryHandler(support_cancel, pattern=r"^shop:"),
        ],
        per_message=False,
        allow_reentry=True,
        conversation_timeout=300,  # 5 min auto-cancel if user abandons
    )
