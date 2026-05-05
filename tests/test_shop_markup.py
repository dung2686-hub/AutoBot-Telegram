import pytest
from src.handlers.shop import calc_min_sell, calc_sell_price

@pytest.mark.asyncio
async def test_calc_sell_price_with_markup():
    # Mock DB object
    class MockDB:
        async def get_markup(self, product_id, default_pct):
            return {"markup_percent": default_pct, "fixed_price": 0}
            
    db = MockDB()
    cost = 100000
    
    # All tiers now use 30% markup
    # calc_min_sell should return max(cost+15k, cost*1.30)
    # min_sell = max(115000, 130000) = 130000
    min_val = calc_min_sell(cost)
    assert min_val == 130000
    
    # calc_sell_price with 30% markup = 130000, rounded up to 10k = 130000
    sell_price = await calc_sell_price(db, "prod1", cost)
    assert sell_price >= min_val
    assert sell_price == 130000

@pytest.mark.asyncio
async def test_calc_sell_price_fixed():
    # Mock DB object
    class MockDB:
        async def get_markup(self, product_id, default_pct):
            return {"markup_percent": 30, "fixed_price": 200000}
            
    db = MockDB()
    cost = 100000
    
    sell_price = await calc_sell_price(db, "prod2", cost)
    # fixed_price is 200,000, which is > min_sell(130,000)
    assert sell_price == 200000

@pytest.mark.asyncio
async def test_round_up_10000():
    """Verify rounding up to nearest 10,000đ."""
    from src.handlers.shop import _round_up_10000
    assert _round_up_10000(130000) == 130000
    assert _round_up_10000(131000) == 140000
    assert _round_up_10000(125001) == 130000
    assert _round_up_10000(10000) == 10000
    assert _round_up_10000(10001) == 20000

@pytest.mark.asyncio
async def test_low_cost_product():
    """Products < 100k should also use 30% markup."""
    class MockDB:
        async def get_markup(self, product_id, default_pct):
            return {"markup_percent": default_pct, "fixed_price": 0}

    db = MockDB()
    cost = 50000
    
    # 50k * 1.30 = 65000, max(65000, 65000) = 65000
    # rounded up to 10k = 70000 (since 65000 is already a multiple? no, 65000 → ceil(65000/10000)*10000 = 70000)
    # Wait: 65000 / 10000 = 6.5 → ceil = 7 → 70000
    sell_price = await calc_sell_price(db, "prod3", cost)
    assert sell_price == 70000
