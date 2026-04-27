from telegram.ext import ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from .states import (
    BROADCAST_MESSAGE,
    CREDIT_INPUT,
    MARKUP_SELECT,
    MARKUP_INPUT,
    NOTE_INPUT,
    CUSTOM_NAME,
    CUSTOM_PRICE,
    CUSTOM_ADD_STOCK,
    CUSTOM_ADD_NOTE,
    CUSTOM_EDIT_MENU,
    CUSTOM_EDIT_NAME,
    CUSTOM_EDIT_PRICE,
    CUSTOM_EDIT_STOCK,
    CUSTOM_EDIT_NOTE,
    CHECKUSER_INPUT,
    QUICKCREDIT_INPUT,
    admin_cancel
)
from .dashboard import admin_command, admin_refresh
from .backup import backup_command
from .users import checkuser_command, checkuser_receive_id, quickcredit_start, quickcredit_execute, credit_start, credit_execute, viewuser_callback, order_lookup as order_lookup
from .broadcast import broadcast_start, broadcast_send
from .markup import markup_menu, markup_prompt, markup_set, markup_toggle, note_edit_prompt, note_save
from .products import (
    custom_list, custom_add_start, custom_add_name, custom_add_price,
    custom_add_stock, custom_add_note, custom_add_note_skip,
    custom_edit_menu, custom_edit_name_prompt, custom_edit_price_prompt,
    custom_edit_name, custom_edit_price, custom_delete,
    custom_edit_stock_prompt, custom_edit_stock,
    custom_edit_note_prompt, custom_edit_note,
)

def get_admin_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_command),  # Included here for completeness, though main.py binds it directly
            CommandHandler("checkuser", checkuser_command),
            CommandHandler("backup", backup_command),
            CallbackQueryHandler(quickcredit_start, pattern=r"^admin:quick(credit|debit):\d+$"),
            CallbackQueryHandler(broadcast_start, pattern=r"^admin:broadcast$"),
            CallbackQueryHandler(credit_start, pattern=r"^admin:credit$"),
            CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            CallbackQueryHandler(custom_add_start, pattern=r"^admin:custom_add$"),
            CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit:\d+$"),
            CallbackQueryHandler(custom_delete, pattern=r"^admin:custom_del:\d+$"),
            CallbackQueryHandler(viewuser_callback, pattern=r"^admin:viewuser:\d+$"),
            CallbackQueryHandler(admin_refresh, pattern=r"^admin:refresh$"),
        ],
        states={
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send),
            ],
            CREDIT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, credit_execute),
            ],
            MARKUP_SELECT: [
                CallbackQueryHandler(markup_prompt, pattern=r"^admin:markup_select:.*$"),
                CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            ],
            MARKUP_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, markup_set),
                CallbackQueryHandler(note_edit_prompt, pattern=r"^admin:note_edit:.*$"),
                CallbackQueryHandler(markup_toggle, pattern=r"^admin:markup_toggle:.*$"),
                CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            ],
            NOTE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, note_save),
                CallbackQueryHandler(markup_menu, pattern=r"^admin:markup$"),
            ],
            CUSTOM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_add_name),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_add_price),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_ADD_STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_add_stock),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_ADD_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_add_note),
                CallbackQueryHandler(custom_add_note_skip, pattern=r"^admin:custom_skip_note$"),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_EDIT_MENU: [
                CallbackQueryHandler(custom_edit_name_prompt, pattern=r"^admin:custom_edit_name$"),
                CallbackQueryHandler(custom_edit_price_prompt, pattern=r"^admin:custom_edit_price$"),
                CallbackQueryHandler(custom_edit_stock_prompt, pattern=r"^admin:custom_edit_stock$"),
                CallbackQueryHandler(custom_edit_note_prompt, pattern=r"^admin:custom_edit_note$"),
                CallbackQueryHandler(custom_list, pattern=r"^admin:custom$"),
            ],
            CUSTOM_EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_edit_name),
                CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit_menu$"),
            ],
            CUSTOM_EDIT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_edit_price),
                CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit_menu$"),
            ],
            CUSTOM_EDIT_STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_edit_stock),
                CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit_menu$"),
            ],
            CUSTOM_EDIT_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_edit_note),
                CallbackQueryHandler(custom_edit_menu, pattern=r"^admin:custom_edit_menu$"),
            ],
            CHECKUSER_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checkuser_receive_id),
            ],
            QUICKCREDIT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, quickcredit_execute),
                CallbackQueryHandler(admin_cancel, pattern=r"^admin:refresh$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(admin_cancel, pattern=r"^(menu:|admin:refresh)"),
        ],
        per_message=False,
        allow_reentry=True,
        conversation_timeout=600,  # 10 min for admin (longer due to complex flows)
    )
