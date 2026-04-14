import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent.parent.parent / "bot.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        await self._conn.executescript(schema)
        await self._migrate()
        await self._conn.commit()
        logger.info("Database initialized: %s", self.db_path)

    async def _migrate(self):
        """Run migrations for schema changes."""
        try:
            await self.conn.execute("ALTER TABLE product_markups ADD COLUMN fixed_price INTEGER DEFAULT 0")
            logger.info("Migration: added fixed_price column")
        except Exception:
            pass
        try:
            await self.conn.execute("ALTER TABLE product_markups ADD COLUMN custom_note TEXT DEFAULT ''")
            logger.info("Migration: added custom_note column")
        except Exception:
            pass

    async def close(self):
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected")
        return self._conn

    # ── Users ─────────────────────────────────────────────

    async def get_or_create_user(self, telegram_id: int, username: str = "", full_name: str = "", lang: str = "vi") -> dict:
        row = await self._fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        if row:
            return dict(row)

        await self.conn.execute(
            "INSERT INTO users (telegram_id, username, full_name, language) VALUES (?, ?, ?, ?)",
            (telegram_id, username, full_name, lang),
        )
        await self.conn.commit()
        row = await self._fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        return dict(row)

    async def get_user(self, telegram_id: int) -> Optional[dict]:
        row = await self._fetch_one(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        return dict(row) if row else None

    async def set_referral(self, telegram_id: int, referrer_id: int) -> bool:
        """Sets referred_by if it's null and not self. Returns True if successfully set."""
        if telegram_id == referrer_id:
            return False
            
        user = await self.get_user(telegram_id)
        if not user or user.get("referred_by"):
            return False
            
        referrer = await self.get_user(referrer_id)
        if not referrer:
            return False
            
        await self.conn.execute(
            "UPDATE users SET referred_by = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ? AND referred_by IS NULL",
            (referrer["id"], telegram_id),
        )
        await self.conn.commit()
        return True

    async def set_user_language(self, telegram_id: int, lang: str):
        """Update user language."""
        await self.conn.execute(
            "UPDATE users SET language = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
            (lang, telegram_id)
        )
        await self.conn.commit()

    async def update_balance(self, telegram_id: int, amount: int) -> int:
        """Add amount to balance (negative to deduct). Returns new balance, or -1 if insufficient."""
        if amount < 0:
            cursor = await self.conn.execute(
                "UPDATE users SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE telegram_id = ? AND balance + ? >= 0",
                (amount, telegram_id, amount),
            )
            if cursor.rowcount == 0:
                return -1
        else:
            await self.conn.execute(
                "UPDATE users SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (amount, telegram_id),
            )
        await self.conn.commit()
        user = await self.get_user(telegram_id)
        return user["balance"]

    async def get_balance(self, telegram_id: int) -> int:
        user = await self.get_user(telegram_id)
        return user["balance"] if user else 0

    async def count_users(self) -> int:
        row = await self._fetch_one("SELECT COUNT(*) as cnt FROM users")
        return row["cnt"] if row else 0

    async def check_and_pay_referral_bonus(self, user_id: int, order_amount: int) -> int:
        """
        Check if this is the first completed order for the user.
        If yes, and they have a referrer, pay 10% bonus to the referrer.
        Returns the amount of bonus paid (0 if none).
        """
        # Check if user has referred_by
        user = await self._fetch_one("SELECT id, telegram_id, referred_by FROM users WHERE id = ?", (user_id,))
        if not user or not user["referred_by"]:
            return 0
            
        # Check if referrer already received bonus for this user
        referrer_id = user["referred_by"]
        check_bonus = await self._fetch_one(
            "SELECT id FROM transactions WHERE user_id = ? AND type = 'referral_bonus' AND reference_id = ?",
            (referrer_id, str(user_id))
        )
        if check_bonus:
            return 0 # Already paid bonus for this user
            
        # Calculate 10% bonus
        bonus_amount = int(order_amount * 0.1)
        if bonus_amount <= 0:
            return 0
            
        referrer = await self._fetch_one("SELECT telegram_id FROM users WHERE id = ?", (referrer_id,))
        if not referrer:
            return 0
            
        # Add bonus to referrer
        new_balance = await self.update_balance(referrer["telegram_id"], bonus_amount)
        await self.add_transaction(
            user_id=referrer_id, 
            tx_type="referral_bonus", 
            amount=bonus_amount,
            balance_after=new_balance, 
            description=f"Hoa hồng 10% (từ user {user_id})", 
            reference_id=str(user_id)
        )
        return bonus_amount

    # ── Deposits ──────────────────────────────────────────

    async def create_deposit(self, user_id: int, amount: int, code: str, expire_minutes: int = 30) -> dict:
        expires_at = datetime.utcnow() + timedelta(minutes=expire_minutes)
        cursor = await self.conn.execute(
            "INSERT INTO deposits (user_id, amount, code, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, amount, code, expires_at.isoformat()),
        )
        await self.conn.commit()
        deposit_id = cursor.lastrowid
        row = await self._fetch_one("SELECT * FROM deposits WHERE id = ?", (deposit_id,))
        return dict(row)

    async def find_pending_deposit(self, code: str) -> Optional[dict]:
        row = await self._fetch_one(
            "SELECT * FROM deposits WHERE code = ? AND status = 'pending'", (code,)
        )
        return dict(row) if row else None

    async def complete_deposit(self, deposit_id: int, reference_code: str = ""):
        await self.conn.execute(
            "UPDATE deposits SET status = 'completed', reference_code = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (reference_code, deposit_id),
        )
        await self.conn.commit()

    async def expire_old_deposits(self) -> list[dict]:
        now = datetime.utcnow().isoformat()
        rows = await self._fetch_all(
            "SELECT * FROM deposits WHERE status = 'pending' AND expires_at < ?",
            (now,),
        )
        if rows:
            await self.conn.execute(
                "UPDATE deposits SET status = 'expired' WHERE status = 'pending' AND expires_at < ?",
                (now,),
            )
            await self.conn.commit()
        return [dict(r) for r in rows]

    async def expire_old_orders(self, minutes: int) -> list[dict]:
        modifier = f"-{int(minutes)} minutes"
        rows = await self._fetch_all(
            "SELECT * FROM orders WHERE status = 'pending' AND created_at < datetime('now', ?)",
            (modifier,),
        )
        if rows:
            await self.conn.execute(
                "UPDATE orders SET status = 'expired' WHERE status = 'pending' AND created_at < datetime('now', ?)",
                (modifier,),
            )
            await self.conn.commit()
        return [dict(r) for r in rows]

    async def get_user_deposits(self, user_id: int, limit: int = 10) -> list[dict]:
        rows = await self._fetch_all(
            "SELECT * FROM deposits WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    # ── Orders ────────────────────────────────────────────

    async def create_order(
        self, user_id: int, product_id: str,
        product_name: str, quantity: int, original_price: int,
        sell_price: int, order_code: str = "", delivered_data: list = None,
        status: str = "completed"
    ) -> dict:
        delivered_data = delivered_data or []
        total = sell_price * quantity
        await self.conn.execute(
            """INSERT INTO orders
            (user_id, order_code, product_id, product_name, quantity,
             original_price, sell_price, total_amount, delivered_data, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, order_code, product_id, product_name, quantity,
             original_price, sell_price, total, json.dumps(delivered_data), status),
        )
        await self.conn.commit()
        row = await self._fetch_one(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        return dict(row)

    async def get_order(self, order_id: int) -> Optional[dict]:
        row = await self._fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))
        return dict(row) if row else None

    async def get_user_order(self, order_id: int, user_id: int) -> Optional[dict]:
        row = await self._fetch_one(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?",
            (order_id, user_id),
        )
        return dict(row) if row else None

    async def update_order(self, order_id: int, status: str, order_code: str = "", delivered_data: list = None):
        if delivered_data is not None:
            await self.conn.execute(
                "UPDATE orders SET status = ?, order_code = ?, delivered_data = ? WHERE id = ?",
                (status, order_code, json.dumps(delivered_data), order_id)
            )
        else:
            await self.conn.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status, order_id)
            )
        await self.conn.commit()

    async def get_user_orders(self, user_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
        rows = await self._fetch_all(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return [dict(r) for r in rows]


    async def count_user_orders(self, user_id: int) -> int:
        row = await self._fetch_one(
            "SELECT COUNT(*) as cnt FROM orders WHERE user_id = ?", (user_id,)
        )
        return row["cnt"] if row else 0

    async def get_total_revenue(self) -> int:
        row = await self._fetch_one("SELECT COALESCE(SUM(total_amount), 0) as total FROM orders WHERE status = 'completed'")
        return row["total"] if row else 0

    async def get_daily_stats(self) -> dict:
        """Get today's order and revenue statistics."""
        orders_row = await self._fetch_one(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(total_amount), 0) as revenue "
            "FROM orders WHERE status = 'completed' AND DATE(created_at) = DATE('now')"
        )
        failed_row = await self._fetch_one(
            "SELECT COUNT(*) as cnt FROM orders WHERE status IN ('failed', 'expired') AND DATE(created_at) = DATE('now')"
        )
        profit_row = await self._fetch_one(
            "SELECT COALESCE(SUM((sell_price - original_price) * quantity), 0) as profit "
            "FROM orders WHERE status = 'completed' AND DATE(created_at) = DATE('now')"
        )
        deposit_row = await self._fetch_one(
            "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = 'deposit' AND DATE(created_at) = DATE('now')"
        )
        new_users_row = await self._fetch_one(
            "SELECT COUNT(*) as cnt FROM users WHERE DATE(created_at) = DATE('now')"
        )
        return {
            "completed": orders_row["cnt"] if orders_row else 0,
            "failed": failed_row["cnt"] if failed_row else 0,
            "revenue": orders_row["revenue"] if orders_row else 0,
            "profit": profit_row["profit"] if profit_row else 0,
            "deposits": deposit_row["total"] if deposit_row else 0,
            "new_users": new_users_row["cnt"] if new_users_row else 0,
        }

    async def get_today_orders_count(self) -> int:
        row = await self._fetch_one(
            "SELECT COUNT(*) as cnt FROM orders WHERE status = 'completed' AND DATE(created_at) = DATE('now')"
        )
        return row["cnt"] if row else 0

    # ── Transactions ──────────────────────────────────────

    async def add_transaction(
        self, user_id: int, tx_type: str, amount: int,
        balance_after: int, description: str = "", reference_id: str = "",
    ):
        await self.conn.execute(
            """INSERT INTO transactions
            (user_id, type, amount, balance_after, description, reference_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, tx_type, amount, balance_after, description, reference_id),
        )
        await self.conn.commit()

    async def get_user_transactions(self, user_id: int, limit: int = 10) -> list[dict]:
        rows = await self._fetch_all(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    # ── Product Markups ───────────────────────────────────

    async def get_markup(self, product_id: str, default: int = 20) -> dict:
        """Returns {'markup_percent': int, 'fixed_price': int}."""
        row = await self._fetch_one(
            "SELECT markup_percent, fixed_price FROM product_markups WHERE product_id = ? AND is_active = 1",
            (product_id,),
        )
        if row:
            return {"markup_percent": row["markup_percent"], "fixed_price": row["fixed_price"] or 0}
        return {"markup_percent": default, "fixed_price": 0}

    async def get_custom_note(self, product_id: str) -> str:
        row = await self._fetch_one(
            "SELECT custom_note FROM product_markups WHERE product_id = ?",
            (product_id,),
        )
        return row["custom_note"] if row and row["custom_note"] else ""

    async def set_custom_note(self, product_id: str, product_name: str, note: str):
        await self.conn.execute(
            """INSERT INTO product_markups (product_id, product_name, custom_note)
            VALUES (?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                custom_note = excluded.custom_note""",
            (product_id, product_name, note),
        )
        await self.conn.commit()

    async def set_markup(self, product_id: str, product_name: str, markup_percent: int, fixed_price: int = 0):
        await self.conn.execute(
            """INSERT INTO product_markups (product_id, product_name, markup_percent, fixed_price)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                product_name = excluded.product_name,
                markup_percent = excluded.markup_percent,
                fixed_price = excluded.fixed_price""",
            (product_id, product_name, markup_percent, fixed_price),
        )
        await self.conn.commit()

    async def get_all_markups(self) -> list[dict]:
        rows = await self._fetch_all("SELECT * FROM product_markups ORDER BY product_name")
        return [dict(r) for r in rows]

    async def get_inactive_product_ids(self) -> set[str]:
        rows = await self._fetch_all("SELECT product_id FROM product_markups WHERE is_active = 0")
        return {r["product_id"] for r in rows}

    async def toggle_markup_active(self, product_id: str, product_name: str, is_active: int):
        await self.conn.execute(
            """INSERT INTO product_markups (product_id, product_name, is_active)
            VALUES (?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                is_active = excluded.is_active""",
            (product_id, product_name, is_active),
        )
        await self.conn.commit()

    # ── All Users (admin) ─────────────────────────────────

    async def get_all_user_ids(self) -> list[int]:
        rows = await self._fetch_all("SELECT telegram_id FROM users")
        return [r["telegram_id"] for r in rows]

    # ── Custom Products ───────────────────────────────────

    async def add_custom_product(self, name: str, price: int) -> dict:
        cursor = await self.conn.execute(
            "INSERT INTO custom_products (name, price) VALUES (?, ?)",
            (name, price),
        )
        await self.conn.commit()
        row = await self._fetch_one("SELECT * FROM custom_products WHERE id = ?", (cursor.lastrowid,))
        return dict(row)

    async def get_custom_products(self) -> list[dict]:
        rows = await self._fetch_all("SELECT * FROM custom_products WHERE is_active = 1 ORDER BY id DESC")
        return [dict(r) for r in rows]

    async def get_custom_product(self, product_id: int) -> Optional[dict]:
        row = await self._fetch_one("SELECT * FROM custom_products WHERE id = ?", (product_id,))
        return dict(row) if row else None

    async def update_custom_product(self, product_id: int, name: str = None, price: int = None):
        if name is not None:
            await self.conn.execute("UPDATE custom_products SET name = ? WHERE id = ?", (name, product_id))
        if price is not None:
            await self.conn.execute("UPDATE custom_products SET price = ? WHERE id = ?", (price, product_id))
        await self.conn.commit()

    async def delete_custom_product(self, product_id: int):
        await self.conn.execute("DELETE FROM custom_products WHERE id = ?", (product_id,))
        await self.conn.commit()

    # ── Helpers ────────────────────────────────────────────

    async def _fetch_one(self, sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchone()

    async def _fetch_all(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchall()
