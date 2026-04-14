import json
from typing import List

from datamodel import Order, OrderDepth, Symbol, TradingState


# Per-product config. slope is drift in price per tick; target is desired inventory.
PRODUCT_CONFIG = {
    "ASH_COATED_OSMIUM":   {"slope": 0.0,   "target": 0,  "limit": 50, "fixed_fair": 10000.0},
    "INTARIAN_PEPPER_ROOT": {"slope": 0.001, "target": 20, "limit": 50, "fixed_fair": None},
}
TRADED_PRODUCTS = set(PRODUCT_CONFIG.keys())

# Pepper root drift anchor: mid ≈ 10000 + 0.001 * global_t
PEPPER_INTERCEPT = 10000.0
PEPPER_SLOPE = 0.001

# Fill-rate tracking (units/tick). Slow EMA so noise doesn't whip τ around.
FILL_EMA_ALPHA = 0.02
FILL_RATE_INIT = 0.003
FILL_RATE_FLOOR = 0.001


def compute_fair(product, order_depth, timestamp, trader_state):
    cfg = PRODUCT_CONFIG[product]
    if cfg["fixed_fair"] is not None:
        return cfg["fixed_fair"]

    if product == "INTARIAN_PEPPER_ROOT":
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        mid = (best_bid + best_ask) / 2.0

        anchor_mid = trader_state.get("pepper_anchor_mid")
        anchor_ts = trader_state.get("pepper_anchor_ts")
        if anchor_mid is None:
            # snap first mid to nearest 1000 — each day starts at a multiple of 1000
            anchor_mid = round(mid / 1000.0) * 1000.0
            anchor_ts = timestamp
            trader_state["pepper_anchor_mid"] = anchor_mid
            trader_state["pepper_anchor_ts"] = anchor_ts

        return anchor_mid + PEPPER_SLOPE * (timestamp - anchor_ts)

    return None


def update_fill_rates(product, state, trader_state):
    """Updates and returns (buy_rate, sell_rate) in units/tick for this product."""
    key_buy = f"fill_buy_{product}"
    key_sell = f"fill_sell_{product}"
    buy_rate = trader_state.get(key_buy, FILL_RATE_INIT)
    sell_rate = trader_state.get(key_sell, FILL_RATE_INIT)

    # own_trades contains only the trades from the previous tick — count them all.
    trades = state.own_trades.get(product, []) if state.own_trades else []
    tick_buy_qty = 0
    tick_sell_qty = 0
    for t in trades:
        if t.buyer == "SUBMISSION":
            tick_buy_qty += t.quantity
        if t.seller == "SUBMISSION":
            tick_sell_qty += t.quantity

    a = FILL_EMA_ALPHA
    buy_rate = a * tick_buy_qty + (1 - a) * buy_rate
    sell_rate = a * tick_sell_qty + (1 - a) * sell_rate
    trader_state[key_buy] = buy_rate
    trader_state[key_sell] = sell_rate
    return max(buy_rate, FILL_RATE_FLOOR), max(sell_rate, FILL_RATE_FLOOR)


class Trader:

    def run(self, state: TradingState):
        try:
            ema_state = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            ema_state = {}

        result = {}

        for product in state.order_depths:
            if product not in TRADED_PRODUCTS:
                continue

            cfg = PRODUCT_CONFIG[product]
            limit = cfg["limit"]
            target = cfg["target"]
            slope = cfg["slope"]

            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            fair = compute_fair(product, order_depth, state.timestamp, ema_state)
            if fair is None:
                result[product] = []
                continue

            buy_rate, sell_rate = update_fill_rates(product, state, ema_state)

            # Direction-specific fair: account for drift over the expected unwind time.
            # Buying pushes pos up; to unwind back to target we need to sell (pos - target) units.
            # Selling pushes pos down; to unwind we need to buy (target - pos) units.
            def fair_for_buy(current_pos: int) -> float:
                new_pos = current_pos + 1
                need_to_sell = max(new_pos - target, 0)
                tau = need_to_sell / sell_rate
                return fair + slope * tau

            def fair_for_sell(current_pos: int) -> float:
                new_pos = current_pos - 1
                need_to_buy = max(target - new_pos, 0)
                tau = need_to_buy / buy_rate
                return fair + slope * tau

            # ---- TAKE ----
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if pos >= limit:
                    break
                if ask_price < fair_for_buy(pos):
                    ask_vol = abs(order_depth.sell_orders[ask_price])
                    buy_qty = min(ask_vol, limit - pos)
                    if buy_qty > 0:
                        orders.append(Order(product, ask_price, buy_qty))
                        pos += buy_qty

            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if pos <= -limit:
                    break
                if bid_price > fair_for_sell(pos):
                    bid_vol = order_depth.buy_orders[bid_price]
                    sell_qty = min(bid_vol, limit + pos)
                    if sell_qty > 0:
                        orders.append(Order(product, bid_price, -sell_qty))
                        pos -= sell_qty

            # ---- MAKE ----
            fb = fair_for_buy(pos)
            fs = fair_for_sell(pos)

            penny_bid = best_bid + 1
            penny_ask = best_ask - 1

            # quotes must be +EV given direction-specific fair
            max_bid = int(fb) if fb > int(fb) else int(fb) - 1
            min_ask = int(fs) + 1 if fs > int(fs) else int(fs) + 1

            if penny_bid > max_bid:
                penny_bid = max_bid
            if penny_ask < min_ask:
                penny_ask = min_ask

            if penny_bid >= penny_ask:
                penny_bid = max_bid
                penny_ask = min_ask
                if penny_bid >= penny_ask:
                    penny_ask = penny_bid + 1

            # skew sizing toward target inventory: full room on the favored side, half on the other
            buy_room = limit - pos
            sell_room = limit + pos
            if pos < target:
                buy_qty_total = buy_room
                sell_qty_total = sell_room // 2
            elif pos > target:
                buy_qty_total = buy_room // 2
                sell_qty_total = sell_room
            else:
                buy_qty_total = buy_room
                sell_qty_total = sell_room

            if buy_qty_total > 0:
                lvl1 = buy_qty_total // 2
                lvl2 = buy_qty_total - lvl1
                if lvl1 > 0:
                    orders.append(Order(product, penny_bid, lvl1))
                if lvl2 > 0:
                    orders.append(Order(product, penny_bid - 1, lvl2))
            if sell_qty_total > 0:
                lvl1 = sell_qty_total // 2
                lvl2 = sell_qty_total - lvl1
                if lvl1 > 0:
                    orders.append(Order(product, penny_ask, -lvl1))
                if lvl2 > 0:
                    orders.append(Order(product, penny_ask + 1, -lvl2))

            result[product] = orders

        conversions = 0
        trader_data = json.dumps(ema_state)
        return result, conversions, trader_data
