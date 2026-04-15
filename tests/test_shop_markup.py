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
    
    # calc_min_sell should return max(cost+15k, cost*1.25)
    # min_sell = max(115000, 125000) = 125000
    min_val = calc_min_sell(cost)
    assert min_val == 125000
    
    # calc_sell_price with 25% markup = 125000, rounded up is 125000
    sell_price = await calc_sell_price(db, "prod1", cost)
    assert sell_price >= min_val
    assert sell_price == 125000

@pytest.mark.asyncio
async def test_calc_sell_price_fixed():
    # Mock DB object
    class MockDB:
        async def get_markup(self, product_id, default_pct):
            return {"markup_percent": 30, "fixed_price": 200000}
            
    db = MockDB()
    cost = 100000
    
    sell_price = await calc_sell_price(db, "prod2", cost)
    # fixed_price is 200,000, which is > min_sell(125,000)
    assert sell_price == 200000
