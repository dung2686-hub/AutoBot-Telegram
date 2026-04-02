import asyncio
import logging
import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

from src.config import config
from src.database.db import Database
from src.services.canboso import CanbosoClient
from src.services import sepay_webhook

from src.handlers.start import start_command, main_menu_callback
from src.handlers.shop import shop_menu, product_detail, quantity_change, buy_confirm, execute_purchase
from src.handlers.wallet import wallet_menu, transaction_history, get_deposit_conversation
from src.handlers.profile import profile_menu
from src.handlers.history import history_menu, history_detail
from src.handlers.support import get_support_conversation
from src.handlers.language import language_menu, language_set
from src.handlers.admin import admin_command, admin_refresh, get_admin_conversation

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """Initialize shared resources after bot starts."""
    db = Database()
    await db.connect()

    canboso = CanbosoClient()
    await canboso.start()
    await canboso.refresh_cache()

    application.bot_data["db"] = db
    application.bot_data["canboso"] = canboso

    # Set up SePay webhook dependencies
    sepay_webhook.set_dependencies(application, db)

    # Start SePay webhook server
    runner = await run_webhook_server()
    application.bot_data["webhook_runner"] = runner

    # Start scheduler for periodic tasks
    scheduler = await run_scheduler(db, canboso)
    application.bot_data["scheduler"] = scheduler

    # Set bot commands (shows in Menu)
    from telegram import BotCommand, MenuButtonCommands
    await application.bot.set_my_commands([
        BotCommand("start", "Bắt đầu và xem menu"),
        BotCommand("admin", "Admin dashboard"),
    ])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    logger.info("Bot initialized successfully")


async def post_shutdown(application: Application):
    """Clean up resources."""
    # Stop scheduler
    scheduler = application.bot_data.get("scheduler")
    if scheduler:
        scheduler.shutdown(wait=False)

    # Stop webhook server
    runner = application.bot_data.get("webhook_runner")
    if runner:
        await runner.cleanup()

    db = application.bot_data.get("db")
    if db:
        await db.close()

    canboso = application.bot_data.get("canboso")
    if canboso:
        await canboso.close()

    logger.info("Bot shutdown complete")


def build_application() -> Application:
    """Build and configure the Telegram bot application."""
    app = Application.builder().token(config.bot_token).post_init(post_init).post_shutdown(post_shutdown).build()

    # ── ConversationHandlers (must be added FIRST) ────────
    app.add_handler(get_deposit_conversation(), group=0)
    app.add_handler(get_support_conversation(), group=1)
    app.add_handler(get_admin_conversation(), group=2)

    # ── Command Handlers ──────────────────────────────────
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))

    # ── Callback Query Handlers ───────────────────────────
    # Main menu
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern=r"^menu:main$"))

    # Shop
    app.add_handler(CallbackQueryHandler(shop_menu, pattern=r"^menu:shop$"))
    app.add_handler(CallbackQueryHandler(product_detail, pattern=r"^shop:detail:"))
    app.add_handler(CallbackQueryHandler(quantity_change, pattern=r"^shop:qty:"))
    app.add_handler(CallbackQueryHandler(buy_confirm, pattern=r"^shop:buy:"))
    app.add_handler(CallbackQueryHandler(execute_purchase, pattern=r"^shop:execute:"))

    # Wallet
    app.add_handler(CallbackQueryHandler(wallet_menu, pattern=r"^menu:wallet$"))
    app.add_handler(CallbackQueryHandler(transaction_history, pattern=r"^wallet:transactions$"))

    # Profile
    app.add_handler(CallbackQueryHandler(profile_menu, pattern=r"^menu:profile$"))

    # History
    app.add_handler(CallbackQueryHandler(history_menu, pattern=r"^menu:history"))
    app.add_handler(CallbackQueryHandler(history_detail, pattern=r"^history:detail:"))

    # Language
    app.add_handler(CallbackQueryHandler(language_menu, pattern=r"^menu:language$"))
    app.add_handler(CallbackQueryHandler(language_set, pattern=r"^lang:"))

    # Admin
    app.add_handler(CallbackQueryHandler(admin_refresh, pattern=r"^admin:refresh$"))

    # No-op (for quantity display button)
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))

    return app


async def run_webhook_server():
    """Run SePay webhook server alongside the bot."""
    webhook_app = sepay_webhook.create_webhook_app()
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, config.webhook_host, config.webhook_port)
    await site.start()
    logger.info("SePay webhook server started on %s:%d", config.webhook_host, config.webhook_port)
    return runner


async def run_scheduler(db: Database, canboso: CanbosoClient):
    """Run periodic tasks."""
    scheduler = AsyncIOScheduler()

    # Expire old deposits every 5 minutes
    scheduler.add_job(db.expire_old_deposits, "interval", minutes=5)

    # Refresh product cache every 1 minute
    scheduler.add_job(canboso.refresh_cache, "interval", minutes=1)

    scheduler.start()
    return scheduler


def main():
    """Main entry point."""
    if not config.bot_token or config.bot_token == "your_bot_token_from_botfather":
        logger.error("❌ TELEGRAM_BOT_TOKEN not set! Copy .env.example to .env and fill in your token.")
        sys.exit(1)

    logger.info("🤖 Starting AI Store Bot...")
    logger.info("📡 SePay webhook will start on port %d", config.webhook_port)

    app = build_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
