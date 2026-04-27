"""
Regression tests for bugfix session 2026-04-27:
1. Admin debit insufficient funds → no ghost transaction
2. QR setup with missing bank config → no orphan pending order
3. QR generation failure → order marked as failed
4. /order → admin:viewuser callback → shows user info
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ──────────────────────────────────────────────

def make_mock_db(user=None, balance=50000):
    """Create a mock DB with configurable user and balance."""
    db = AsyncMock()
    default_user = {
        "id": 1,
        "telegram_id": 12345,
        "username": "testuser",
        "full_name": "Test User",
        "balance": balance,
        "language": "vi",
        "created_at": "2026-01-01T00:00:00",
        "referred_by": None,
    }
    db.get_user.return_value = user or default_user
    db.get_balance.return_value = balance
    db.get_user_transactions.return_value = []
    db.get_user_deposits.return_value = []
    db.get_user_orders.return_value = []
    return db


def make_mock_update(callback_data=None, message_text=None, user_id=12345):
    """Create a mock Update object."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id

    if callback_data:
        query = AsyncMock()
        query.data = callback_data
        query.message = AsyncMock()
        query.message.reply_text = AsyncMock()
        update.callback_query = query
        update.message = None
    else:
        update.callback_query = None
        update.message = AsyncMock()
        update.message.text = message_text or ""
        update.message.reply_text = AsyncMock()

    return update


def make_mock_context(db, user_data=None, bot_data=None):
    """Create a mock context."""
    context = MagicMock()
    context.user_data = user_data or {}
    context.bot_data = bot_data or {"db": db}
    context.bot = AsyncMock()
    context.application = MagicMock()
    return context


# ── Test 1: Admin debit insufficient funds ───────────────

class TestDebitInsufficientFunds:
    """quickcredit_execute should stop when update_balance returns -1."""

    @pytest.mark.asyncio
    async def test_debit_blocked_no_transaction(self):
        """When user has insufficient funds, no transaction should be created."""
        from src.handlers.admin.users import quickcredit_execute

        db = make_mock_db(balance=50000)
        db.update_balance.return_value = -1  # Insufficient funds

        update = make_mock_update(message_text="100000")
        context = make_mock_context(db, user_data={
            "active_conv": "admin_quickcredit",
            "quickcredit_target": 12345,
            "quickcredit_debit": True,
        })
        # ensure_user decorator needs db_user
        context.user_data["db_user"] = {"id": 1, "telegram_id": 99999, "language": "vi"}

        with patch("src.handlers.admin.users.admin_keyboard", return_value=None):
            result = await quickcredit_execute.__wrapped__.__wrapped__.__wrapped__(update, context)

        # Should NOT call add_transaction
        db.add_transaction.assert_not_called()

        # Should reply with error message
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "không đủ số dư" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_debit_success_creates_transaction(self):
        """When debit succeeds, transaction should be created."""
        from src.handlers.admin.users import quickcredit_execute

        db = make_mock_db(balance=50000)
        db.update_balance.return_value = 0  # Success: 50k - 50k = 0

        update = make_mock_update(message_text="50000")
        context = make_mock_context(db, user_data={
            "active_conv": "admin_quickcredit",
            "quickcredit_target": 12345,
            "quickcredit_debit": True,
        })
        context.user_data["db_user"] = {"id": 1, "telegram_id": 99999, "language": "vi"}

        with patch("src.handlers.admin.users.admin_keyboard", return_value=None):
            result = await quickcredit_execute.__wrapped__.__wrapped__.__wrapped__(update, context)

        # Should call add_transaction
        db.add_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_credit_always_succeeds(self):
        """Credit (cộng tiền) should always work regardless of balance."""
        from src.handlers.admin.users import quickcredit_execute

        db = make_mock_db(balance=0)
        db.update_balance.return_value = 100000  # 0 + 100k

        update = make_mock_update(message_text="100000")
        context = make_mock_context(db, user_data={
            "active_conv": "admin_quickcredit",
            "quickcredit_target": 12345,
            "quickcredit_debit": False,  # Credit, not debit
        })
        context.user_data["db_user"] = {"id": 1, "telegram_id": 99999, "language": "vi"}

        with patch("src.handlers.admin.users.admin_keyboard", return_value=None):
            result = await quickcredit_execute.__wrapped__.__wrapped__.__wrapped__(update, context)

        db.add_transaction.assert_called_once()


# ── Test 2: QR setup bank config validation order ────────

class TestQrBankConfigValidation:
    """Bank config should be checked BEFORE creating a pending order."""

    @pytest.mark.asyncio
    async def test_qr_pay_no_order_when_bank_missing(self):
        """qr_pay_setup should NOT create order if bank config is empty."""
        from src.handlers.shop import qr_pay_setup

        db = make_mock_db()
        mock_canboso = MagicMock()
        mock_canboso.find_product.return_value = {
            "_id": "prod1",
            "product_name": "Test",
            "walletPricing": 50000,
            "stats": {"available": 10},
        }

        update = make_mock_update(callback_data="shop:qr_pay:prod1:1")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 12345, "language": "vi"},
        })
        context.bot_data["canboso"] = mock_canboso

        with patch("src.handlers.shop.config") as mock_config, \
             patch("src.handlers.shop.calc_sell_price", new_callable=AsyncMock, return_value=65000):
            mock_config.bank_bin = ""
            mock_config.bank_account = ""

            await qr_pay_setup.__wrapped__.__wrapped__(update, context)

        # create_order should NOT be called
        db.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_qr_pay_creates_order_when_bank_configured(self):
        """qr_pay_setup SHOULD create order when bank config exists."""
        from src.handlers.shop import qr_pay_setup

        db = make_mock_db()
        db.create_order.return_value = {"id": 42}

        mock_canboso = MagicMock()
        mock_canboso.find_product.return_value = {
            "_id": "prod1",
            "product_name": "Test",
            "walletPricing": 50000,
            "stats": {"available": 10},
        }

        update = make_mock_update(callback_data="shop:qr_pay:prod1:1")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 12345, "language": "vi"},
        })
        context.bot_data["canboso"] = mock_canboso

        with patch("src.handlers.shop.config") as mock_config, \
             patch("src.handlers.shop.calc_sell_price", new_callable=AsyncMock, return_value=65000), \
             patch("src.handlers.shop.generate_qr_image", new_callable=AsyncMock, return_value=b"fake_qr"), \
             patch("src.handlers.shop.get_bank_display_name", return_value="Vietcombank"):
            mock_config.bank_bin = "970436"
            mock_config.bank_account = "123456789"
            mock_config.bank_account_name = "NGUYEN VAN A"

            await qr_pay_setup.__wrapped__.__wrapped__(update, context)

        db.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_qr_pay_no_order_when_bank_missing(self):
        """custom_qr_pay_setup should NOT create order if bank config is empty."""
        from src.handlers.shop import custom_qr_pay_setup

        db = make_mock_db()
        db.get_custom_product.return_value = {
            "id": 1, "name": "Canva", "price": 30000, "stock": 5, "is_active": 1,
        }

        update = make_mock_update(callback_data="custom:qr_pay:1:1")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 12345, "language": "vi"},
        })

        with patch("src.handlers.shop.config") as mock_config:
            mock_config.bank_bin = ""
            mock_config.bank_account = ""

            await custom_qr_pay_setup.__wrapped__.__wrapped__(update, context)

        db.create_order.assert_not_called()


# ── Test 3: QR generation failure → order marked failed ──

class TestQrGenerationFailure:
    """If generate_qr_image crashes, pending order should be marked failed."""

    @pytest.mark.asyncio
    async def test_qr_failure_marks_order_failed(self):
        """qr_pay_setup: QR crash → update_order(status=failed)."""
        from src.handlers.shop import qr_pay_setup

        db = make_mock_db()
        db.create_order.return_value = {"id": 99}

        mock_canboso = MagicMock()
        mock_canboso.find_product.return_value = {
            "_id": "prod1",
            "product_name": "Test",
            "walletPricing": 50000,
        }

        update = make_mock_update(callback_data="shop:qr_pay:prod1:1")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 12345, "language": "vi"},
        })
        context.bot_data["canboso"] = mock_canboso

        with patch("src.handlers.shop.config") as mock_config, \
             patch("src.handlers.shop.calc_sell_price", new_callable=AsyncMock, return_value=65000), \
             patch("src.handlers.shop.generate_qr_image", new_callable=AsyncMock, side_effect=Exception("QR API down")):
            mock_config.bank_bin = "970436"
            mock_config.bank_account = "123456789"

            await qr_pay_setup.__wrapped__.__wrapped__(update, context)

        # Order should be marked as failed
        db.update_order.assert_called_once_with(99, status="failed")

    @pytest.mark.asyncio
    async def test_custom_qr_failure_marks_order_failed(self):
        """custom_qr_pay_setup: QR crash → update_order(status=failed)."""
        from src.handlers.shop import custom_qr_pay_setup

        db = make_mock_db()
        db.get_custom_product.return_value = {
            "id": 1, "name": "Canva", "price": 30000, "stock": 5, "is_active": 1,
        }
        db.create_order.return_value = {"id": 77}

        update = make_mock_update(callback_data="custom:qr_pay:1:1")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 12345, "language": "vi"},
        })

        with patch("src.handlers.shop.config") as mock_config, \
             patch("src.handlers.shop.generate_qr_image", new_callable=AsyncMock, side_effect=Exception("timeout")):
            mock_config.bank_bin = "970436"
            mock_config.bank_account = "123456789"

            await custom_qr_pay_setup.__wrapped__.__wrapped__(update, context)

        db.update_order.assert_called_once_with(77, status="failed")


# ── Test 4: /order viewuser callback routing ─────────────

class TestViewuserCallback:
    """admin:viewuser callback should show user info, not quickcredit flow."""

    @pytest.mark.asyncio
    async def test_viewuser_shows_user_info(self):
        """viewuser_callback should reply with user info text."""
        from src.handlers.admin.users import viewuser_callback

        db = make_mock_db(balance=150000)

        update = make_mock_update(callback_data="admin:viewuser:12345")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 99999, "language": "vi"},
        })

        await viewuser_callback.__wrapped__.__wrapped__.__wrapped__(update, context)

        # Should call reply_text (send new message), not edit
        query = update.callback_query
        query.message.reply_text.assert_called_once()

        call_args = query.message.reply_text.call_args
        text = call_args[0][0]
        assert "THÔNG TIN USER" in text
        assert "12345" in text
        assert "Test User" in text

    @pytest.mark.asyncio
    async def test_viewuser_has_credit_debit_buttons(self):
        """viewuser_callback should include quick credit/debit buttons."""
        from src.handlers.admin.users import viewuser_callback

        db = make_mock_db()

        update = make_mock_update(callback_data="admin:viewuser:12345")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 99999, "language": "vi"},
        })

        await viewuser_callback.__wrapped__.__wrapped__.__wrapped__(update, context)

        call_kwargs = update.callback_query.message.reply_text.call_args[1]
        markup = call_kwargs.get("reply_markup")
        assert markup is not None

        # Extract all callback_data from keyboard
        all_callbacks = []
        for row in markup.inline_keyboard:
            for btn in row:
                all_callbacks.append(btn.callback_data)

        assert "admin:quickcredit:12345" in all_callbacks
        assert "admin:quickdebit:12345" in all_callbacks

    @pytest.mark.asyncio
    async def test_viewuser_user_not_found(self):
        """viewuser_callback should handle missing user gracefully."""
        from src.handlers.admin.users import viewuser_callback

        db = make_mock_db()
        db.get_user.return_value = None

        update = make_mock_update(callback_data="admin:viewuser:99999")
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 99999, "language": "vi"},
        })

        await viewuser_callback.__wrapped__.__wrapped__.__wrapped__(update, context)

        call_args = update.callback_query.message.reply_text.call_args
        assert "Không tìm thấy" in call_args[0][0]


# ── Test: /order button callback_data is viewuser ────────

class TestOrderButtonCallback:
    """The 'Xem user' button in /order should use admin:viewuser, not admin:quickcredit."""

    @pytest.mark.asyncio
    async def test_order_button_uses_viewuser_callback(self):
        """order_lookup keyboard should contain admin:viewuser, not admin:quickcredit."""
        from src.handlers.admin.users import order_lookup

        db = make_mock_db()
        db.get_order.return_value = {
            "id": 59, "user_id": 1, "order_code": "CB123",
            "product_id": "prod1", "product_name": "Test Product",
            "quantity": 1, "original_price": 50000, "sell_price": 65000,
            "total_amount": 65000, "status": "completed",
            "created_at": "2026-04-27T00:00:00", "delivered_data": "[]",
        }
        db.get_user_by_id.return_value = {
            "id": 1, "telegram_id": 12345, "username": "testuser",
            "full_name": "Test User",
        }

        update = make_mock_update(message_text="/order 59")
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        context = make_mock_context(db, user_data={
            "db_user": {"id": 1, "telegram_id": 99999, "language": "vi"},
        })
        context.args = ["59"]

        await order_lookup.__wrapped__.__wrapped__.__wrapped__(update, context)

        call_kwargs = update.message.reply_text.call_args[1]
        markup = call_kwargs.get("reply_markup")

        # Extract all callback_data
        all_callbacks = []
        for row in markup.inline_keyboard:
            for btn in row:
                all_callbacks.append(btn.callback_data)

        # Must be viewuser, NOT quickcredit
        assert any("admin:viewuser:" in cb for cb in all_callbacks)
        assert not any("admin:quickcredit:" in cb for cb in all_callbacks)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
