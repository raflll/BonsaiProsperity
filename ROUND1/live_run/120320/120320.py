import json
from typing import List

from datamodel import Order, OrderDepth, Symbol, TradingState


# Per-product config. slope is drift in price per tick; target is desired inventory.
PRODUCT_CONFIG = {
    "ASH_COATED_OSMIUM":   {"slope": 0.0,   "target": 0,  "limit": 80, "fixed_fair": 10000.0},
    "INTARIAN_PEPPER_ROOT": {"slope": 0.001, "target": 20, "limit": 80, "fixed_fair": None},
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

        # Exit near end of run. Live runs ~100k ticks; backtest runs ~1M.
        # Exit in the last 1k ticks of either length. On backtest the trader will
        # briefly flatten at 99k-100k then re-accumulate for the remaining 900k —
        # cost of that detour is trivial (~50 seashells of missed drift).
        ts = state.timestamp
        in_exit_window = (99_000 <= ts < 100_000) or ts >= 999_000

        for product in state.order_depths:
            if product not in TRADED_PRODUCTS:
                continue

            cfg = PRODUCT_CONFIG[product]
            limit = cfg["limit"]

            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            if product == "ASH_COATED_OSMIUM":
                # No drift — classic market making around 10000.
                fair = 10000
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    if ask_price < fair and pos < limit:
                        ask_vol = abs(order_depth.sell_orders[ask_price])
                        buy_qty = min(ask_vol, limit - pos)
                        if buy_qty > 0:
                            orders.append(Order(product, ask_price, buy_qty))
                            pos += buy_qty
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    if bid_price > fair and pos > -limit:
                        bid_vol = order_depth.buy_orders[bid_price]
                        sell_qty = min(bid_vol, limit + pos)
                        if sell_qty > 0:
                            orders.append(Order(product, bid_price, -sell_qty))
                            pos -= sell_qty
                penny_bid = min(best_bid + 1, fair - 1)
                penny_ask = max(best_ask - 1, fair + 1)
                buy_room = limit - pos
                sell_room = limit + pos
                if buy_room > 0:
                    orders.append(Order(product, penny_bid, buy_room))
                if sell_room > 0:
                    orders.append(Order(product, penny_ask, -sell_room))
            elif in_exit_window:
                # Unwind by posting passive offers — save the spread vs. hitting bids.
                if pos > 0:
                    orders.append(Order(product, best_ask - 1, -pos))
                elif pos < 0:
                    orders.append(Order(product, best_bid + 1, -pos))
            else:
                # Accumulate to +limit by posting a passive bid — save the spread vs. lifting asks.
                if pos < limit:
                    orders.append(Order(product, best_bid + 1, limit - pos))

            result[product] = orders

        conversions = 0
        trader_data = json.dumps(ema_state)
        return result, conversions, trader_data