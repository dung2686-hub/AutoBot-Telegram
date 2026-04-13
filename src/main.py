import asyncio
import logging
import shutil
import sys
from datetime import datetime
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
from src.handlers.shop import shop_menu, product_detail, quantity_change, buy_confirm, execute_purchase, qr_pay_setup, custom_product_detail
from src.handlers.wallet import wallet_menu, transaction_history, get_deposit_conversation
from src.handlers.profile import profile_menu
from src.handlers.history import history_menu, history_detail
from src.handlers.support import get_support_conversation
from src.handlers.language import language_menu, language_set
from src.handlers.admin import admin_command, admin_refresh, backup_command, get_admin_conversation

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
    scheduler = await run_scheduler(application, db, canboso)
    application.bot_data["scheduler"] = scheduler

    # Set bot commands (shows in Menu)
    from telegram import BotCommand, MenuButtonCommands
    await application.bot.set_my_commands([
        BotCommand("start", "Bắt đầu và xem menu"),
        BotCommand("admin", "Admin dashboard"),
        BotCommand("checkuser", "Kiểm tra user (admin)"),
        BotCommand("backup", "Tải DB ngay (admin)"),
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
    app.add_handler(CommandHandler("backup", backup_command))

    # ── Callback Query Handlers ───────────────────────────
    # Main menu
    from src.handlers.start import language_menu_callback, set_language_callback, api_menu_callback
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern=r"^menu:main$"))
    app.add_handler(CallbackQueryHandler(language_menu_callback, pattern=r"^menu:language$"))
    app.add_handler(CallbackQueryHandler(api_menu_callback, pattern=r"^menu:api$"))
    app.add_handler(CallbackQueryHandler(set_language_callback, pattern=r"^lang:(.*)$"))

    # Shop
    app.add_handler(CallbackQueryHandler(shop_menu, pattern=r"^menu:shop$"))
    app.add_handler(CallbackQueryHandler(product_detail, pattern=r"^shop:detail:"))
    app.add_handler(CallbackQueryHandler(quantity_change, pattern=r"^shop:qty:"))
    app.add_handler(CallbackQueryHandler(buy_confirm, pattern=r"^shop:buy:"))
    app.add_handler(CallbackQueryHandler(execute_purchase, pattern=r"^shop:execute:"))
    app.add_handler(CallbackQueryHandler(qr_pay_setup, pattern=r"^shop:qr_pay:"))

    # Custom Shop
    app.add_handler(CallbackQueryHandler(custom_product_detail, pattern=r"^custom:detail:"))

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


async def run_scheduler(application, db: Database, canboso: CanbosoClient):
    """Run periodic tasks."""
    scheduler = AsyncIOScheduler()

    async def check_expirations():
        try:
            # Expire deposits
            expired_deposits = await db.expire_old_deposits()
            for deposit in expired_deposits:
                user = await db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (deposit["user_id"],))
                if user and user["telegram_id"]:
                    try:
                        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                        from src.utils.formatters import format_vnd as _fv
                        dep_amount = deposit.get('amount', 0)
                        msg = (
                            f"⏱ <b>Yêu cầu nạp ví NAP{deposit['id']} đã hết hạn!</b>\n\n"
                            f"💰 Số tiền: <b>{_fv(dep_amount)}</b>\n\n"
                            f"Đơn nạp bị hủy do chưa nhận được thanh toán trong {config.deposit_expire_minutes} phút.\n"
                            f"⚠️ <i>Nếu bạn đã chuyển khoản, hệ thống sẽ tự động cộng tiền vào ví khi nhận được.</i>"
                        )
                        kb = InlineKeyboardMarkup([
                            [InlineKeyboardButton("💳 Xem ví", callback_data="menu:wallet")],
                            [InlineKeyboardButton("📋 Menu chính", callback_data="menu:main")]
                        ])
                        await application.bot.send_message(
                            chat_id=user["telegram_id"], text=msg,
                            reply_markup=kb, parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Cannot send deposit expiry to {user['telegram_id']}: {e}")
            
            # Expire orders (MUA)
            # Default to 5 minutes expiration for QR orders
            expired_orders = await db.expire_old_orders(minutes=5)
            for order in expired_orders:
                user = await db._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (order["user_id"],))
                if user and user["telegram_id"]:
                    try:
                        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                        from src.utils.formatters import format_vnd
                        product_name = order.get('product_name', 'Sản phẩm')
                        total = order.get('total_amount', 0)
                        msg = (
                            f"⏱ <b>Đơn hàng MUA{order['id']} đã hết hạn!</b>\n\n"
                            f"📦 Sản phẩm: <b>{product_name}</b>\n"
                            f"💰 Số tiền: <b>{format_vnd(total)}</b>\n\n"
                            f"Đơn bị hủy do chưa nhận được thanh toán trong 5 phút.\n"
                            f"⚠️ <i>Nếu bạn đã chuyển khoản, hệ thống sẽ tự động hoàn tiền vào ví khi nhận được.</i>"
                        )
                        kb = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛒 Mua lại", callback_data=f"shop:detail:{order['product_id']}")],
                            [InlineKeyboardButton("📋 Menu chính", callback_data="menu:main")]
                        ])
                        await application.bot.send_message(
                            chat_id=user["telegram_id"], text=msg,
                            reply_markup=kb, parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Cannot send order expiry to {user['telegram_id']}: {e}")
        except Exception as e:
            logger.error(f"Error in expiration task: {e}")

    async def backup_database():
        """Auto backup SQLite DB to admin Telegram."""
        try:
            db_path = Path(db.db_path)
            if not db_path.exists():
                logger.warning("Backup skipped: DB file not found")
                return

            # WAL checkpoint — flush WAL to main DB for clean backup
            await db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

            from src.utils.formatters import now_vn
            vn_now = now_vn()
            timestamp = vn_now.strftime("%Y%m%d_%H%M")
            backup_path = db_path.parent / f"bot_backup_{timestamp}.db"
            shutil.copy2(str(db_path), str(backup_path))

            users_count = await db.count_users()
            revenue = await db.get_total_revenue()

            with open(str(backup_path), "rb") as f:
                await application.bot.send_document(
                    chat_id=config.admin_chat_id,
                    document=f,
                    caption=(
                        f"🗄 <b>Auto Backup</b>\n"
                        f"📅 {vn_now.strftime('%d/%m/%Y %H:%M')}\n"
                        f"👥 Users: {users_count}\n"
                        f"💰 Revenue: {revenue:,}đ\n"
                        f"📦 Size: {backup_path.stat().st_size / 1024:.1f} KB"
                    ),
                    parse_mode="HTML",
                )

            backup_path.unlink(missing_ok=True)
            logger.info("Database backup sent to admin")
        except Exception as e:
            logger.error(f"Backup failed: {e}")

    async def check_and_broadcast_restocks():
        try:
            if not getattr(canboso, "pending_restocks", []):
                return

            restocks = canboso.pending_restocks[:]
            canboso.pending_restocks.clear()

            user_ids = await db.get_all_user_ids()
            if not user_ids:
                return

            msg = "🚀 <b>HÀNG MỚI VỪA VỀ</b>\n\n"
            from src.utils.formatters import shorten_product_name
            for r in restocks:
                short_name = shorten_product_name(r['name'])
                msg += f"📦 <b>{short_name}</b>\n➕ Thêm: {r['added']}\n📦 Tồn kho hiện tại: {r['total']}\n\n"
            msg += "👉 Mở Menu Hoặc Bấm Nút Mua Ngay Bên Dưới Nhé!"

            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            if len(restocks) == 1:
                pid = restocks[0]['product_id']
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Mua ngay", callback_data=f"shop:detail:{pid}")]])
            else:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Mở Shop", callback_data="menu:shop")]])

            # Broadcast safely
            for uid in user_ids:
                try:
                    await application.bot.send_message(chat_id=uid, text=msg, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error in broadcast task: {e}")

    # Run check broadcast every 1 minute
    scheduler.add_job(check_and_broadcast_restocks, "interval", minutes=1)

    # Run expiration check every 1 minute
    scheduler.add_job(check_expirations, "interval", minutes=1)

    # Refresh product cache every 1 minute
    scheduler.add_job(canboso.refresh_cache, "interval", minutes=1)

    # Auto backup every 6 hours
    scheduler.add_job(backup_database, "interval", hours=6)

    # Daily summary at 23:59 VN time (= 16:59 UTC)
    async def daily_summary():
        try:
            if not config.admin_chat_id:
                return
            from src.utils.formatters import format_vnd, now_vn
            stats = await db.get_daily_stats()
            total_users = await db.count_users()
            date_str = now_vn().strftime("%d/%m/%Y")
            msg = (
                f"📊 <b>BÁO CÁO NGÀY {date_str}</b>\n\n"
                f"🛒 Đơn hàng: {stats['completed']} ✅ / {stats['failed']} ❌\n"
                f"💰 Doanh thu: {format_vnd(stats['revenue'])}\n"
                f"📊 Lãi ròng: +{format_vnd(stats['profit'])}\n"
                f"💳 Nạp ví: {format_vnd(stats['deposits'])}\n"
                f"👥 Khách mới: {stats['new_users']} (Tổng: {total_users})"
            )
            await application.bot.send_message(chat_id=config.admin_chat_id, text=msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Daily summary failed: {e}")

    scheduler.add_job(daily_summary, "cron", hour=16, minute=59)  # 23:59 VN

    scheduler.start()
    logger.info("Scheduler started: expiration(1m), cache(1m), backup(6h)")
    return scheduler


def main():
    """Main entry point."""
    if not config.bot_token or config.bot_token == "your_bot_token_from_botfather":
        logger.error("❌ TELEGRAM_BOT_TOKEN not set! Copy .env.example to .env and fill in your token.")
        sys.exit(1)

    logger.info("🤖 Starting AI Store Bot... [BUILD v2-debug]")
    logger.info("📡 SePay webhook will start on port %d", config.webhook_port)

    app = build_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
