import json
from typing import List

from datamodel import Order, OrderDepth, Symbol, TradingState


# Per-product config. slope is drift in price per tick; target is desired inventory.
PRODUCT_CONFIG = {
    "ASH_COATED_OSMIUM":   {"slope": 0.0,   "target": 0,  "limit": 80, "fixed_fair": 10000.0},
    "INTARIAN_PEPPER_ROOT": {"slope": 0.001, "target": 80, "limit": 80, "fixed_fair": None},
}
TRADED_PRODUCTS = set(PRODUCT_CONFIG.keys())

DAY_TICKS = 1_000_000
EXIT_BUFFER = 1_000

# Pepper root drift.
PEPPER_SLOPE = 0.001
# EMA alpha for self-correcting pepper anchor (mid - slope*t).
PEPPER_ANCHOR_EMA_ALPHA = 0.2

# Osmium: cap per-side quote sizes so one aggressor can't flip us to ±limit.
OSMIUM_PENNY_CAP = 25   # tight quote at best_bid+1 / best_ask-1
OSMIUM_DEEP_CAP = 15    # deeper quote one tick further out

# Osmium long-run anchor (strict +EV sweep level) and short EMA for regime fair.
# Anchor stays at 10000 — buys strictly <10000 / sells strictly >10000 are
# pure edge. EMA-adjusted fair drives quote placement so we don't post dead
# quotes at 9999/10001 when the regime is trading at e.g. 10003.
OSMIUM_ANCHOR = 10000
OSMIUM_EMA_ALPHA = 0.05
# Clamp regime fair within this band around anchor to cap tail-chasing risk.
OSMIUM_REGIME_CAP = 10

# Max premium over fair we'll pay when lifting pepper asks. Above this, wait for
# either a cheaper ask or a passive fill. Calibrated on 3-day backtest:
# unbounded threshold = 282,821; cap=7 = 283,174 (+353 shells).
PEPPER_LIFT_CAP_OVER_FAIR = 7


def compute_fair(product, order_depth, timestamp, trader_state):
    cfg = PRODUCT_CONFIG[product]
    if cfg["fixed_fair"] is not None:
        return cfg["fixed_fair"]

    if product == "INTARIAN_PEPPER_ROOT":
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        mid = (best_bid + best_ask) / 2.0

        # Self-correcting anchor: intercept = mid - slope*t, EMA'd over time.
        implied_intercept = mid - PEPPER_SLOPE * timestamp
        anchor = trader_state.get("pepper_anchor_intercept")
        if anchor is None:
            # Seed with nearest-1000 snap — days start at multiples of 1000.
            anchor = round(implied_intercept / 1000.0) * 1000.0
        a = PEPPER_ANCHOR_EMA_ALPHA
        anchor = a * implied_intercept + (1 - a) * anchor
        trader_state["pepper_anchor_intercept"] = anchor

        return anchor + PEPPER_SLOPE * timestamp

    return None


class Trader:

    def run(self, state: TradingState):
        try:
            ema_state = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            ema_state = {}

        result = {}

        # Fix 1: exit window repeats every day (modulo day length), so multi-day
        # backtests re-enter and re-accumulate correctly.
        ts = state.timestamp
        ticks_into_day = ts % DAY_TICKS
        in_exit_window = ticks_into_day >= (DAY_TICKS - EXIT_BUFFER)
        ticks_remaining_in_day = DAY_TICKS - ticks_into_day

        for product in state.order_depths:
            if product not in TRADED_PRODUCTS:
                continue

            cfg = PRODUCT_CONFIG[product]
            limit = cfg["limit"]
            target = cfg["target"]

            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            if product == "ASH_COATED_OSMIUM":
                anchor = OSMIUM_ANCHOR
                mid = (best_bid + best_ask) / 2.0
                ema_fair = ema_state.get("osmium_ema_fair", float(anchor))
                ema_fair = OSMIUM_EMA_ALPHA * mid + (1 - OSMIUM_EMA_ALPHA) * ema_fair
                # Clamp to guard against tail excursions dragging fair too far.
                ema_fair = max(anchor - OSMIUM_REGIME_CAP,
                               min(anchor + OSMIUM_REGIME_CAP, ema_fair))
                ema_state["osmium_ema_fair"] = ema_fair
                fair_q = int(round(ema_fair))  # regime fair on the tick grid

                pos_start = pos
                buy_budget = limit - pos_start
                sell_budget = limit + pos_start

                # Sweep strictly crossed prices vs long-run anchor (pure +EV).
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    if ask_price < anchor and buy_budget > 0:
                        ask_vol = abs(order_depth.sell_orders[ask_price])
                        buy_qty = min(ask_vol, buy_budget)
                        orders.append(Order(product, ask_price, buy_qty))
                        buy_budget -= buy_qty
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    if bid_price > anchor and sell_budget > 0:
                        bid_vol = order_depth.buy_orders[bid_price]
                        sell_qty = min(bid_vol, sell_budget)
                        orders.append(Order(product, bid_price, -sell_qty))
                        sell_budget -= sell_qty

                # Sweep prices at regime fair only when they reduce |pos| (exit at
                # current regime mean, not just at anchor — lets us flatten in a
                # 10003 regime even when no one is bidding 10000).
                if pos < 0 and fair_q in order_depth.sell_orders:
                    ask_vol = abs(order_depth.sell_orders[fair_q])
                    buy_qty = min(ask_vol, -pos, buy_budget)
                    if buy_qty > 0:
                        orders.append(Order(product, fair_q, buy_qty))
                        buy_budget -= buy_qty
                if pos > 0 and fair_q in order_depth.buy_orders:
                    bid_vol = order_depth.buy_orders[fair_q]
                    sell_qty = min(bid_vol, pos, sell_budget)
                    if sell_qty > 0:
                        orders.append(Order(product, fair_q, -sell_qty))
                        sell_budget -= sell_qty

                # Skip penny if spread is too tight to make.
                spread = best_ask - best_bid
                if spread > 1:
                    # Quotes ride the regime fair, not the anchor. In a 10003
                    # regime this posts penny_bid=10002 instead of the old 9999.
                    penny_bid = min(best_bid + 1, fair_q - 1)
                    penny_ask = max(best_ask - 1, fair_q + 1)
                    # Deep (at bid / ask) listed first so market trades at bid/ask
                    # fill at bid/ask instead of at penny (bid+1 / ask-1), saving 1
                    # shell per unit. Backtest gain: +4,673 shells / 3 days.
                    deep_bid = penny_bid - 1
                    deep_ask = penny_ask + 1
                    deep_buy_qty = min(buy_budget, OSMIUM_DEEP_CAP)
                    deep_sell_qty = min(sell_budget, OSMIUM_DEEP_CAP)
                    if deep_buy_qty > 0 and deep_bid < fair_q:
                        orders.append(Order(product, deep_bid, deep_buy_qty))
                        buy_budget -= deep_buy_qty
                    if deep_sell_qty > 0 and deep_ask > fair_q:
                        orders.append(Order(product, deep_ask, -deep_sell_qty))
                        sell_budget -= deep_sell_qty
                    # Penny overflow: fires only when trade vol exceeds deep cap.
                    penny_buy_qty = min(buy_budget, OSMIUM_PENNY_CAP)
                    penny_sell_qty = min(sell_budget, OSMIUM_PENNY_CAP)
                    if penny_buy_qty > 0:
                        orders.append(Order(product, penny_bid, penny_buy_qty))
                        buy_budget -= penny_buy_qty
                    if penny_sell_qty > 0:
                        orders.append(Order(product, penny_ask, -penny_sell_qty))
                        sell_budget -= penny_sell_qty
            elif in_exit_window:
                # Fix 3: exit floor — never post below fair + slope * ticks_remaining_in_day.
                fair = compute_fair(product, order_depth, ts, ema_state)
                ev_floor = fair + cfg["slope"] * ticks_remaining_in_day
                if pos > 0:
                    sell_price = int(max(best_ask - 1, round(ev_floor)))
                    orders.append(Order(product, sell_price, -pos))
                elif pos < 0:
                    buy_price = int(min(best_bid + 1, round(ev_floor)))
                    orders.append(Order(product, buy_price, -pos))
            else:
                # Entry: sweep +EV asks, then passive bid with queue-priority check.
                fair = compute_fair(product, order_depth, ts, ema_state)
                exit_ts_in_day = DAY_TICKS - EXIT_BUFFER
                ticks_to_exit = max(0, exit_ts_in_day - ticks_into_day)
                lift_threshold = min(
                    fair + cfg["slope"] * ticks_to_exit,
                    fair + PEPPER_LIFT_CAP_OVER_FAIR,
                )
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    if ask_price <= lift_threshold and pos < target:
                        ask_vol = abs(order_depth.sell_orders[ask_price])
                        buy_qty = min(ask_vol, target - pos)
                        if buy_qty > 0:
                            orders.append(Order(product, ask_price, buy_qty))
                            pos += buy_qty
                if pos < target:
                    passive_price = best_bid + 1
                    if passive_price < best_ask:
                        orders.append(Order(product, passive_price, target - pos))

            result[product] = orders

        conversions = 0
        trader_data = json.dumps(ema_state)
        return result, conversions, trader_data
