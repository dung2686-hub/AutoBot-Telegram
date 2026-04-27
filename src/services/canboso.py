import logging
from typing import Optional

import httpx

from src.config import config

logger = logging.getLogger(__name__)


class CanbosoClient:
    """Async client for Canboso API (Bot B)."""

    def __init__(self):
        self._base_url = config.canboso_api_url
        self._key = config.canboso_api_key
        self._client: Optional[httpx.AsyncClient] = None
        self._products_cache: list[dict] = []
        self._last_stock: dict[str, int] = {}
        self.pending_restocks: list[dict] = []

    async def start(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        logger.info("Canboso client started")

    async def close(self):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Canboso client not started")
        return self._client

    async def get_products(self, use_cache: bool = True) -> list[dict]:
        if use_cache and self._products_cache:
            return self._products_cache

        try:
            resp = await self.client.get(
                f"{self._base_url}/telegram-buyer/products",
                params={"key": self._key},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("success"):
                products = data.get("products", data.get("data", []))
                if isinstance(products, list):
                    new_stock = {}
                    for p in products:
                        pid = p.get("_id")
                        avail = p.get("stats", {}).get("available") or 0
                        if pid:
                            new_stock[pid] = avail
                            if pid in self._last_stock:
                                old_avail = self._last_stock[pid] or 0
                                if avail > old_avail:
                                    self.pending_restocks.append({
                                        "product_id": pid,
                                        "name": p.get("product_name", pid),
                                        "added": avail - old_avail,
                                        "total": avail
                                    })
                    self._last_stock = new_stock
                    self._products_cache = products
                else:
                    self._products_cache = []
                return self._products_cache

            logger.warning("Canboso products failed: %s", data)
            return self._products_cache or []

        except httpx.HTTPError as e:
            logger.error("Canboso products error: %s", e)
            return self._products_cache or []

    async def get_balance(self) -> dict:
        try:
            resp = await self.client.get(
                f"{self._base_url}/telegram-buyer/balance",
                params={"key": self._key},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Canboso balance error: %s", e)
            return {"success": False, "balance": 0, "currency": "VND"}

    async def purchase(
        self,
        product_id: str,
        quantity: int = 1,
        customer_email: str = "",
        slot_months: int = 0,
    ) -> dict:
        body = {"product_id": product_id, "quantity": quantity}
        if customer_email:
            body["customer_email"] = customer_email
        if slot_months:
            body["slot_months"] = slot_months

        try:
            resp = await self.client.post(
                f"{self._base_url}/telegram-buyer/purchase",
                params={"key": self._key},
                json=body,
            )
            data = resp.json()

            if resp.status_code == 200:
                return {"success": True, **data}

            fallback_map = {
                400: "Bad request",
                401: "Invalid API key",
                404: "Product not found",
                409: "Out of stock",
            }
            api_msg = data.get("message") or data.get("error")
            msg = api_msg or fallback_map.get(resp.status_code, f"HTTP {resp.status_code}")
            logger.warning("Canboso purchase failed [%d]: %s | body: %s", resp.status_code, msg, data)
            return {"success": False, "message": msg, "status_code": resp.status_code}

        except httpx.HTTPError as e:
            logger.error("Canboso purchase error: %s", e)
            return {"success": False, "message": str(e)}

    async def refresh_cache(self):
        await self.get_products(use_cache=False)
        logger.info("Products cache refreshed: %d products", len(self._products_cache))

    def find_product(self, product_id: str) -> Optional[dict]:
        for p in self._products_cache:
            if p.get("_id") == product_id:
                return p
        return None
