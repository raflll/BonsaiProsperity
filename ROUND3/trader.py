import json
from typing import List

from datamodel import Order, OrderDepth, TradingState


VEV_STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]

POSITION_LIMITS = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    **{f"VEV_{k}": 300 for k in VEV_STRIKES},
}


class Trader:

    def run(self, state: TradingState):
        try:
            trader_state = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_state = {}

        result = {}

        for product in state.order_depths:
            orders: List[Order] = []
            result[product] = orders

        conversions = 0
        trader_data = json.dumps(trader_state)
        return result, conversions, trader_data
