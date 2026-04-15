import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.formatters import esc
from src.utils.keyboards import main_menu_keyboard, language_keyboard
from src.utils.formatters import format_account_list, format_vnd, esc

logger = logging.getLogger(__name__)

BOT_NAME = "AI Store Bot"


@error_handler
@ensure_user
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — show welcome + main menu in 4 blocks."""
    bot = context.bot
    telegram_id = update.effective_user.id
    first_name = update.effective_user.first_name
    db = context.bot_data["db"]

    # 1. Handle deep linking for referral
    args = context.args
    if args and len(args) > 0:
        arg = args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.split("_")[1])
                # Save referral
                await db.set_referral(telegram_id, referrer_id)
            except ValueError:
                pass

    bot_info = await bot.get_me()
    bot_username = bot_info.username
    bot_display_name = bot_info.first_name

    ref_link = f"https://t.me/{bot_username}?start=ref_{telegram_id}"

    # Block 1: Welcome & Referral Program
    msg1 = (
        f"👋 Xin chào {first_name} đã đến với <b>{esc(bot_display_name)}</b>!\n\n"
        f"🎁 Chương trình giới thiệu bạn bè\n\n"
        f"• Chia sẻ link bot kèm mã giới thiệu của bạn.\n"
        f"• Khi người được mời phát sinh đơn hàng đầu tiên, bạn nhận 10% giá trị đơn vào ví.\n"
        f"• Mỗi người mới chỉ được tính thưởng 1 lần.\n"
        f"• Không áp dụng cho tự giới thiệu.\n\n"
        f"🔗 Link giới thiệu của bạn:\n{ref_link}"
    )

    # Block 2: Promo
    msg2 = (
        f"🎁 Khuyến mãi:\n"
        f"🛍️ Mua số lượng nhiều sẽ tự động có chiết khấu theo chính sách hiện hành!"
    )

    # Block 3 & 4: Guide and Menu
    msg3 = (
        f"📌 Hướng dẫn nhanh:\n"
        f"1. Nhấn nút \"🛍️ Mua hàng\".\n"
        f"2. Chọn sản phẩm bạn muốn mua.\n"
        f"3. Chọn thanh toán bằng QR và quét mã để thanh toán.\n"
        f"4. Sau khi thanh toán xong, bot sẽ tự động xử lý đơn hàng."
    )
    
    lang = context.user_data.get("lang", "vi")
    msg4 = t("menu_prompt", lang) if t("menu_prompt", lang) != "menu_prompt" else "📌 Vui lòng chọn menu:"
    
    keyboard = main_menu_keyboard(lang=lang)

    # Send blocks sequentially
    await update.message.reply_text(msg1, disable_web_page_preview=True, parse_mode="HTML")
    await update.message.reply_text(msg2, parse_mode="HTML")
    await update.message.reply_text(msg3, parse_mode="HTML")
    await update.message.reply_text(msg4, reply_markup=keyboard, parse_mode="HTML")


@error_handler
@ensure_user
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback to return to main menu."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    text = f"📌 Vui lòng chọn menu:"
    keyboard = main_menu_keyboard(lang=lang)

    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        # If text is exactly the same, Telegram raises BadRequest
        pass

@error_handler
@ensure_user
async def language_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # We can fetch the current user's lang, but let's just show options
    text = "🌐 Vui lòng chọn ngôn ngữ / Please select your language:"
    await query.edit_message_text(text, reply_markup=language_keyboard(), parse_mode="HTML")

@error_handler
@ensure_user
async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    telegram_id = update.effective_user.id
    
    # extract lang from data (e.g., lang:vi)
    lang = query.data.split(":")[1]
    await db.set_user_language(telegram_id, lang)
    
    # After setting language, reload main menu
    text = f"✅ Ngôn ngữ đã được thay đổi / Language has been changed.\n\n📌 Vui lòng chọn menu:"
    keyboard = main_menu_keyboard(lang=lang)
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass

@error_handler
@ensure_user
async def api_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer(text="Tính năng Liên kết API đang được phát triển! Sắp ra mắt.", show_alert=True)

