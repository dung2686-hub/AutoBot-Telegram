import asyncio
import json
import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.sepay_webhook import create_webhook_app
from src.config import config

class MockDB:
    def __init__(self):
        self.processed = []
        
    async def get_processed_webhook(self, reference_code):
        for p in self.processed:
            if p["reference_code"] == reference_code:
                return p
        return None

    async def get_deposit_by_id(self, deposit_id):
        return {"id": deposit_id, "user_id": 1, "status": "pending"}

    async def get_user_by_id(self, user_id):
        return {"telegram_id": 999999, "full_name": "Test User"}

    async def complete_deposit(self, deposit_id, reference_code):
        pass

    async def update_balance(self, telegram_id, amount):
        return 10000

    async def add_transaction(self, **kwargs):
        pass

    async def check_and_pay_referral_bonus(self, user_id, amount):
        return 0

    class MockConn:
        async def execute(self, query, params):
            class MockCursor:
                rowcount = 1
            return MockCursor()

        async def commit(self):
            pass

    @property
    def conn(self):
        return self.MockConn()

class TestSePayWebhook(AioHTTPTestCase):
    async def get_application(self):
        # Override config secret for testing
        config.sepay_secret_key = "test_secret"
        
        # Inject Mock DB 
        mock_db = MockDB()
        
        return create_webhook_app(bot_app=None, db=mock_db)

    @unittest_run_loop
    async def test_missing_dependencies_500(self):
        # Temporarily remove db from app context 
        old_db = self.app.get('db')
        self.app['db'] = None
        
        resp = await self.client.post("/webhook/sepay", headers={"Authorization": "test_secret"}, json={})
        self.assertEqual(resp.status, 500)
        
        # Restore db
        self.app['db'] = old_db

    @unittest_run_loop
    async def test_invalid_secret_401(self):
        resp = await self.client.post("/webhook/sepay", headers={"Authorization": "wrong_secret"}, json={})
        self.assertEqual(resp.status, 401)

    @unittest_run_loop
    async def test_rate_limiter_429(self):
        # Fire 31 identical requests quickly
        payload = {"transferType": "in", "content": "NAP 123", "transferAmount": 10000, "referenceCode": "TEST1"}
        headers = {"Authorization": "test_secret"}
        for i in range(30):
            req = await self.client.post("/webhook/sepay", headers=headers, json=payload)
            self.assertEqual(req.status, 200)

        # 31st request from same IP should get 429
        req = await self.client.post("/webhook/sepay", headers=headers, json=payload)
        self.assertEqual(req.status, 429)

    @unittest_run_loop
    async def test_duplicate_request_idempotency(self):
        # Use a fresh app client to avoid rate limit from previous test
        payload = {"transferType": "in", "content": "NAP 123", "transferAmount": 10000, "referenceCode": "DUP1"}
        headers = {"Authorization": "test_secret"}
        
        # Manually force db to report an existing completed webhook
        self.app["db"].processed.append({"reference_code": "DUP1", "status": "completed"})
        
        req = await self.client.post("/webhook/sepay", headers=headers, json=payload)
        self.assertEqual(req.status, 200)
        
        data = await req.json()
        self.assertTrue(data.get("success"))
        # It's completed gracefully without throwing error 

if __name__ == '__main__':
    import unittest
    unittest.main()
