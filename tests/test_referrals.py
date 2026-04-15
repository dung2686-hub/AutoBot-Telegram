import asyncio
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.referral import process_referral_bonus

class MockDB:
    def __init__(self):
        self.bonus_paid = False
        
    async def check_and_pay_referral_bonus(self, user_id: int, total_amount: float) -> float:
        # Simulate business logic: 10% bonus if not paid yet
        if not self.bonus_paid:
            self.bonus_paid = True
            return int(total_amount * 0.1)
        return 0

    async def _fetch_one(self, query, params):
        if "referred_by FROM users" in query:
            return {"full_name": "Buyer Name", "referred_by": 99}
        if "telegram_id, full_name" in query:
            return {"telegram_id": 999999, "full_name": "Referrer Name"}
        return None

class MockBotApp:
    def __init__(self):
        self.bot = self.MockBot()
    
    class MockBot:
        def __init__(self):
            self.messages = []
            
        async def send_message(self, chat_id, text, parse_mode=None):
            self.messages.append({"chat_id": chat_id, "text": text})

def test_referral_bonus_pays_first_time():
    asyncio.run(_test_referral_bonus_pays_first_time())

async def _test_referral_bonus_pays_first_time():
    db = MockDB()
    app = MockBotApp()
    
    # 1. First order -> should pay bonus
    paid = await process_referral_bonus(db, app, order_id=1, user_id=1, total_amount=100000)
    assert paid == True
    
    # Check messages sent to referrer
    referrer_msgs = [m for m in app.bot.messages if m["chat_id"] == 999999]
    assert len(referrer_msgs) == 1
    assert "Chúc mừng!" in referrer_msgs[0]["text"]
    assert "10.000" in referrer_msgs[0]["text"] # 10% of 100k

def test_referral_bonus_idempotent():
    asyncio.run(_test_referral_bonus_idempotent())

async def _test_referral_bonus_idempotent():
    db = MockDB()
    app = MockBotApp()
    
    # 1. First time
    paid1 = await process_referral_bonus(db, app, order_id=1, user_id=1, total_amount=100000)
    assert paid1 == True
    
    # Clear messages
    app.bot.messages = []
    
    # 2. Second time exact same setup -> DB returns 0 because already paid
    paid2 = await process_referral_bonus(db, app, order_id=2, user_id=1, total_amount=100000)
    assert paid2 == False
    
    # Ensure no duplicate message is sent
    assert len(app.bot.messages) == 0

if __name__ == "__main__":
    pytest.main(["-v", __file__])
