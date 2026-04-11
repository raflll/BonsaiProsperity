import json
import math
from datamodel import OrderDepth, TradingState, Order
from typing import List

# ======================== TUNABLE PARAMETERS ========================
PARAMS = {
    "EMERALDS": {
        "gamma": .1,           # A-S risk aversion — higher = wider spreads, less inventory risk
        "kappa_default": 1.5,  # initial kappa before we have enough book data to estimate
        "kappa_ema": 0.1,      # how fast kappa adapts (0 = frozen, 1 = fully reactive)
        "position_limit": 80,
        "order_size": 40,      # neutral-inventory size per side
        "num_levels": 3,       # price levels to quote on each side of the spread
    },
    "TOMATOES": {
        "gamma": .1,
        "kappa_default": 1.5,
        "kappa_ema": 0.1,
        "position_limit": 80,
        "order_size": 40,
        "num_levels": 3,
    },
}

T = 2000000  # 2000 ticks * 100 timestamp units per tick
# ====================================================================


class Trader:

    def run(self, state: TradingState):
        if state.traderData and state.traderData != "":
            trader_state = json.loads(state.traderData)
        else:
            trader_state = {}

        result = {}

        for product in state.order_depths:
            if product not in PARAMS:
                result[product] = []
                continue

            params = PARAMS[product]
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid = (best_bid + best_ask) / 2.0

            # Per-product persistent state: midprice history + running kappa estimate
            if product not in trader_state:
                trader_state[product] = {"history": [], "kappa": params["kappa_default"],
                                         "prev_book": None}
            pstate = trader_state[product]
            pstate["history"].append(mid)
            history = pstate["history"]

            q = state.position.get(product, 0)
            gamma = params["gamma"]
            pos_limit = params["position_limit"]
            order_size = params["order_size"]

            # ---- Kappa estimation from order book shape ----
            # In A-S, fill intensity decays as lambda(delta) = A * exp(-kappa * delta).
            # We estimate kappa by looking at how resting volume drops off with distance
            # from mid: if volume halves every tick, kappa ~ ln(2).
            vol_by_dist = {}
            for price, qty in order_depth.buy_orders.items():
                dist = round(mid - price)
                if dist >= 0:
                    vol_by_dist[dist] = vol_by_dist.get(dist, 0) + abs(qty)
            for price, qty in order_depth.sell_orders.items():
                dist = round(price - mid)
                if dist >= 0:
                    vol_by_dist[dist] = vol_by_dist.get(dist, 0) + abs(qty)

            # Pairwise log-ratio between adjacent levels gives a local kappa estimate.
            # Average across all adjacent pairs, then EMA-smooth across ticks.
            sorted_dists = sorted(vol_by_dist.keys())
            kappa_obs = None
            if len(sorted_dists) >= 2:
                estimates = []
                for j in range(len(sorted_dists) - 1):
                    d1, d2 = sorted_dists[j], sorted_dists[j + 1]
                    v1, v2 = vol_by_dist[d1], vol_by_dist[d2]
                    if v1 > 0 and v2 > 0 and d2 > d1:
                        k = -math.log(v2 / v1) / (d2 - d1)
                        if k > 0:
                            estimates.append(k)
                if estimates:
                    kappa_obs = sum(estimates) / len(estimates)

            alpha = params["kappa_ema"]
            if kappa_obs is not None:
                pstate["kappa"] = alpha * kappa_obs + (1 - alpha) * pstate["kappa"]
            kappa = max(0.01, pstate["kappa"])

            # ---- Volatility (sigma^2) from tick-to-tick midprice changes ----
            n = len(history)
            if n < 3:
                sigma2 = 1.0
            else:
                returns = [history[i] - history[i - 1] for i in range(1, n)]
                mean_r = sum(returns) / len(returns)
                sigma2 = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)

            # ---- Avellaneda-Stoikov core ----
            tau = max((T - state.timestamp) / T, 0.001)
            reservation_price = mid - q * gamma * sigma2 * tau
            spread = gamma * sigma2 * tau + (2.0 / gamma) * math.log(1 + gamma / kappa)

            bid_price = int(round(reservation_price - spread / 2.0))
            ask_price = int(round(reservation_price + spread / 2.0))

            if bid_price >= ask_price:
                bid_price = ask_price - 1

            # ---- Inventory-aware sizing ----
            # Scale total quantity so the side that alleviates our position gets more size.
            # At q=+50, limit=80: buy_total = 20*(1-0.625) = 7, sell_total = 20*(1+0.625) = 33
            num_levels = params["num_levels"]
            inventory_ratio = q / pos_limit
            buy_total = int(round(order_size * (1 - inventory_ratio)))
            sell_total = int(round(order_size * (1 + inventory_ratio)))

            buy_total = max(0, min(buy_total, pos_limit - q))
            sell_total = max(0, min(sell_total, pos_limit + q))

            # ---- Quadratic layering ----
            # Weights [9, 16, 25] for 3 levels — most size at best price, least at deepest.
            raw_weights = [(i + 2) ** 2 for i in range(num_levels)]
            total_weight = sum(raw_weights)

            buy_remaining = buy_total
            for i in range(num_levels):
                if buy_remaining <= 0:
                    break
                level_qty = max(1, int(round(buy_total * raw_weights[i] / total_weight)))
                level_qty = min(level_qty, buy_remaining)
                orders.append(Order(product, bid_price - i, level_qty))
                buy_remaining -= level_qty

            sell_remaining = sell_total
            for i in range(num_levels):
                if sell_remaining <= 0:
                    break
                level_qty = max(1, int(round(sell_total * raw_weights[i] / total_weight)))
                level_qty = min(level_qty, sell_remaining)
                orders.append(Order(product, ask_price + i, -level_qty))
                sell_remaining -= level_qty

            result[product] = orders

        traderData = json.dumps(trader_state)
        conversions = 0
        return result, conversions, traderData
