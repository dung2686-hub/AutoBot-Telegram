import logging
import shutil
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from src.utils.decorators import ensure_user, admin_only, error_handler
from src.utils.formatters import format_vnd, now_vn

logger = logging.getLogger(__name__)

@error_handler
@ensure_user
@admin_only
async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /backup — instantly download DB file."""
    db = context.bot_data["db"]
    db_path = Path(db.db_path)

    if not db_path.exists():
        await update.message.reply_text("❌ File DB không tồn tại.")
        return

    await update.message.reply_text("⏳ Đang chuẩn bị backup...")

    try:
        # WAL checkpoint for clean backup
        await db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        vn_now = now_vn()
        timestamp = vn_now.strftime("%Y%m%d_%H%M%S")
        backup_path = db_path.parent / f"bot_backup_{timestamp}.db"
        shutil.copy2(str(db_path), str(backup_path))

        users_count = await db.count_users()
        revenue = await db.get_total_revenue()

        with open(str(backup_path), "rb") as f:
            await update.message.reply_document(
                document=f,
                caption=(
                    f"🗄 <b>Manual Backup</b>\n"
                    f"📅 {vn_now.strftime('%d/%m/%Y %H:%M:%S')}\n"
                    f"👥 Users: {users_count}\n"
                    f"💰 Revenue: {format_vnd(revenue)}\n"
                    f"📦 Size: {backup_path.stat().st_size / 1024:.1f} KB"
                ),
                parse_mode="HTML",
            )

        backup_path.unlink(missing_ok=True)
    except Exception as e:
        logger.error("Manual backup failed: %s", e)
        await update.message.reply_text(f"❌ Backup thất bại: {e}")
