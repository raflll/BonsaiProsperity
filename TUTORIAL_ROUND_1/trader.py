from datamodel import OrderDepth, TradingState, Order
from typing import List

FAIR_VALUES = {
    "EMERALDS": 10000,
}

POSITION_LIMITS = {
    "EMERALDS": 50,
    "TOMATOES": 50,
}


class Trader:

    def run(self, state: TradingState):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)
            limit = POSITION_LIMITS.get(product, 50)

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            # Fair value: hard-coded if we have one, otherwise use mid
            if product in FAIR_VALUES:
                fair = FAIR_VALUES[product]
            else:
                fair = (best_bid + best_ask) / 2.0

            # ---- TAKE: aggressively hit mispriced orders ----
            # Buy everything offered below fair value
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if ask_price < fair and pos < limit:
                    ask_vol = abs(order_depth.sell_orders[ask_price])  # sell_orders are negative
                    buy_qty = min(ask_vol, limit - pos)
                    if buy_qty > 0:
                        orders.append(Order(product, ask_price, buy_qty))
                        pos += buy_qty

            # Sell into everything bid above fair value
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if bid_price > fair and pos > -limit:
                    bid_vol = order_depth.buy_orders[bid_price]
                    sell_qty = min(bid_vol, limit + pos)
                    if sell_qty > 0:
                        orders.append(Order(product, bid_price, -sell_qty))
                        pos -= sell_qty

            # ---- MAKE: penny the current book ----
            # Post 1 tick better than current best bid/ask
            penny_bid = best_bid + 1
            penny_ask = best_ask - 1

            # Don't cross fair value with our passive orders
            if penny_bid >= fair:
                penny_bid = int(fair) - 1
            if penny_ask <= fair:
                penny_ask = int(fair) + 1

            # Don't let our quotes cross each other
            if penny_bid >= penny_ask:
                penny_bid = int(fair) - 1
                penny_ask = int(fair) + 1

            buy_room = limit - pos
            sell_room = limit + pos

            if buy_room > 0:
                orders.append(Order(product, penny_bid, buy_room))
            if sell_room > 0:
                orders.append(Order(product, penny_ask, -sell_room))

            result[product] = orders

        conversions = 0
        return result, conversions, ""
