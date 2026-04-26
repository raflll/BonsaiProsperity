import json
import math
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

# ── Products ─────────────────────────────────────────────────────────────────

VEV_STRIKES   = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
DEAD_STRIKES  = {6000, 6500}   # stuck at 0.5 mid, essentially zero BS value

POSITION_LIMITS: Dict[str, int] = {
    "HYDROGEL_PACK":       200,
    "VELVETFRUIT_EXTRACT": 200,
    **{f"VEV_{k}": 300 for k in VEV_STRIKES},
}

# ── Black-Scholes ─────────────────────────────────────────────────────────────
SIGMA = 0.2435

VEV_SIGMA_TABLE: Dict[int, float] = {
    4000: 0.2435, 4500: 0.2435,
    5000: 0.241,
    5100: 0.239,
    5200: 0.242,
    5300: 0.244,
    5400: 0.230,
    5500: 0.248,
    6000: 0.2435, 6500: 0.2435,
}

# ── HYDROGEL_PACK ─────────────────────────────────────────────────────────────
# Data: mean ≈ 9990, std ≈ 25–38, spread = 15–17 shells, HL ≈ 189–419 ticks.
HG_ANCHOR          = 10000
HG_EMA_ALPHA       = 0.05
HG_REGIME_CAP      = 10      # clamp EMA within ±10 of anchor
HG_SOFT_LIMIT      = 60      # normal inventory cap (30% of position limit)
HG_SWEEP_THRESHOLD = 35      # min unclamped-EMA deviation before sweeping (plateau 30-50 gives ~54K; comp fires at anchor-73+)
HG_SKEW_PER_UNIT   = 0.08   # shells of fair-value shift per unit of inventory
HG_DEEP_CAP        = 10      # passive size at deep level
HG_PENNY_CAP       = 15      # passive size at penny level

# Warmup: competition first 5% of day — EMA unsettled, use tighter limits
HG_WARMUP_SOFT_LIMIT      = 15
HG_WARMUP_SWEEP_THRESHOLD = 50  # stricter than normal (35) during warmup when ema_unclamped is still settling
HG_WARMUP_PENNY_CAP       = 5
HG_WARMUP_DEEP_CAP        = 0
# Ramp-down: fraction of day length so it scales correctly at any tick rate
HG_RAMP_FRACTION = 0.20   # begin winding down at 80% through each day

# VEV_5200 is skipped in competition: historical sigma=24.2% but competition IV=34–42%.
# Model sees edge to sell, but competition prices at true higher vol → systematic loss.
COMPETITION_SKIP_STRIKES: set = {5200, 5300, 5400, 5500}

# ── VELVETFRUIT_EXTRACT ────────────────────────────────────────────────────────
# Data: HL ≈ 200–350 ticks, spread = 5 shells, std ≈ 14–17 shells.
# Pure inventory-skewed market making: post inside the 5-shell spread,
# skew fair value toward the side we need to reduce.
VEV_EMA_ALPHA     = 0.004   # slow EMA tracks intra-day drift (HL ≈ 173 ticks)
VEV_QUOTE_OFFSET  = 1       # shells inside fair on each side (net 3-shell spread we offer)
VEV_QUOTE_SIZE    = 10      # units per passive quote
VEV_SOFT_LIMIT    = 80      # inventory cap before quoting stops
VEV_SKEW_PER_UNIT = 0.05   # shells of fair-value shift per unit of inventory

# ── VEV options ────────────────────────────────────────────────────────────────
OPT_QUOTE_OFFSET: Dict[int, int] = {
    4000: 5, 4500: 5,
    5000: 10, 5100: 10, 5200: 10, 5300: 10, 5400: 8, 5500: 8,
}
OPT_QUOTE_SIZE      = 6
OPT_AGGRESSIVE_EDGE = 7.5
OPT_PASSIVE_EDGE    = 4.5

OPT_AGG_EDGE_BUY:  Dict[int, float] = {k: OPT_AGGRESSIVE_EDGE for k in VEV_STRIKES}
OPT_AGG_EDGE_SELL: Dict[int, float] = {k: OPT_AGGRESSIVE_EDGE for k in VEV_STRIKES}
OPT_PASS_EDGE_BUY:  Dict[int, float] = {k: OPT_PASSIVE_EDGE for k in VEV_STRIKES}
OPT_PASS_EDGE_SELL: Dict[int, float] = {k: OPT_PASSIVE_EDGE for k in VEV_STRIKES}

OPT_SOFT_LIMIT = 80

# ── Math ──────────────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bs_call(S: float, K: float, T_years: float, sigma: float) -> float:
    if T_years <= 1e-9 or sigma <= 1e-9 or S <= 0:
        return max(0.0, S - K)
    sqrtT = math.sqrt(T_years)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T_years) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)

def bs_call_delta(S: float, K: float, T_years: float, sigma: float) -> float:
    if T_years <= 1e-9 or sigma <= 1e-9 or S <= 0:
        return 1.0 if S > K else 0.0
    sqrtT = math.sqrt(T_years)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T_years) / (sigma * sqrtT)
    return _norm_cdf(d1)

# ── Trader ────────────────────────────────────────────────────────────────────

class Trader:
    def run(self, state: TradingState):
        try:
            ts_state: dict = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            ts_state = {}

        result: Dict[str, List[Order]] = {}

        # ── Day tracking + auto-detect environment ────────────────────────────
        ts      = state.timestamp
        last_ts = ts_state.get("last_ts", ts)
        day_idx = ts_state.get("day_idx", 0)

        if ts < last_ts:
            tick_step = ts_state.get("tick_step", 100)
            ts_state["day_ticks"] = last_ts + tick_step
            day_idx += 1

        if ts > last_ts:
            ts_state["tick_step"] = ts - last_ts

        day_ticks = ts_state.get("day_ticks", 100_000)

        # Detect environment by observed max timestamp: backtest days reach 1M
        if ts >= 100_000:
            day_ticks = 1_000_000
            ts_state["day_ticks"] = day_ticks

        is_competition = (day_ticks == 100_000)
        base_tte = 5.0 if is_competition else 8.0

        ts_state["last_ts"] = ts
        ts_state["day_idx"] = day_idx

        # ── Time to expiry ────────────────────────────────────────────────────
        TTE_days  = max(0.0, base_tte - day_idx - ts / day_ticks)
        TTE_years = TTE_days / 365.0

        # ── Warmup: first 5% of each competition day ──────────────────────────
        in_warmup = is_competition and (ts % day_ticks) < (day_ticks // 20)

        # ── VEV underlying mid ────────────────────────────────────────────────
        vev_mid: float | None = None
        vev_od = state.order_depths.get("VELVETFRUIT_EXTRACT")
        if vev_od and vev_od.buy_orders and vev_od.sell_orders:
            vev_mid = (max(vev_od.buy_orders) + min(vev_od.sell_orders)) / 2.0

        # ── VEV z-score from previous tick (for options anticipatory mid) ───────
        # Written by the VEV block; read here so options always have a valid
        # value regardless of product iteration order in the loop below.
        vev_z = ts_state.get("vev_z", 0.0)

        # ── Portfolio delta (for options skew) ────────────────────────────────
        net_options_delta = 0.0
        if vev_mid is not None and not in_warmup:
            for prod, position in state.position.items():
                if prod.startswith("VEV_") and position != 0:
                    try:
                        k_strike = int(prod.split("_")[1])
                        opt_sig  = VEV_SIGMA_TABLE.get(k_strike, SIGMA)
                        delta    = bs_call_delta(vev_mid, k_strike, TTE_years, opt_sig)
                        net_options_delta += position * delta
                    except ValueError:
                        pass

        portfolio_delta = net_options_delta + state.position.get("VELVETFRUIT_EXTRACT", 0)

        # ── Per-product logic ─────────────────────────────────────────────────
        for product, od in state.order_depths.items():
            if not od.buy_orders or not od.sell_orders:
                result[product] = []
                continue

            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            mid      = (best_bid + best_ask) / 2.0
            pos      = state.position.get(product, 0)
            limit    = POSITION_LIMITS.get(product, 0)
            orders: List[Order] = []

            buy_room  = limit - pos
            sell_room = limit + pos

            # ── HYDROGEL_PACK ─────────────────────────────────────────────────
            # Structure: strong anchor at 10000, spread 15–17 shells, HL ≈ 200–400 ticks.
            # Strategy: sweep when EMA deviates meaningfully from anchor (momentum-gated),
            # then passive MM with inventory skew around skewed fair value.
            if product == "HYDROGEL_PACK":
                # Keep a SEPARATE unclamped EMA for direction detection.
                # The clamped EMA freezes at anchor±cap during sustained displacement,
                # making ema_rising permanently False even when price bounces back.
                # The unclamped EMA tracks actual price, so any bounce registers as rising.
                ema_unclamped_prev = ts_state.get("hg_ema_unclamped", float(HG_ANCHOR))
                var_prev = ts_state.get("hg_var", 0.0)
                diff         = mid - ema_unclamped_prev
                ema_unclamped = HG_EMA_ALPHA * mid + (1.0 - HG_EMA_ALPHA) * ema_unclamped_prev
                var          = HG_EMA_ALPHA * diff**2 + (1.0 - HG_EMA_ALPHA) * var_prev
                ema          = max(HG_ANCHOR - HG_REGIME_CAP, min(HG_ANCHOR + HG_REGIME_CAP, ema_unclamped))
                ts_state["hg_ema"]          = ema
                ts_state["hg_ema_unclamped"] = ema_unclamped
                ts_state["hg_var"]          = var

                ema_rising  = ema_unclamped > ema_unclamped_prev
                ema_falling = ema_unclamped < ema_unclamped_prev

                # Inventory-skewed fair: long position shifts fair down, encouraging sells
                skew   = pos * HG_SKEW_PER_UNIT
                fair_q = int(round(ema - skew))

                soft_limit      = HG_WARMUP_SOFT_LIMIT if in_warmup else HG_SOFT_LIMIT
                sweep_threshold = HG_WARMUP_SWEEP_THRESHOLD if in_warmup else HG_SWEEP_THRESHOLD
                penny_cap       = HG_WARMUP_PENNY_CAP if in_warmup else HG_PENNY_CAP
                deep_cap        = HG_WARMUP_DEEP_CAP  if in_warmup else HG_DEEP_CAP

                tick_in_day   = ts % day_ticks
                ticks_to_exit = day_ticks - tick_in_day

                if is_competition:
                    if not in_warmup:
                        warmup_end         = day_ticks // 20
                        ramp_up_ticks      = max(1, day_ticks // 10)
                        ticks_since_warmup = tick_in_day - warmup_end
                        if 0 <= ticks_since_warmup < ramp_up_ticks:
                            up_frac    = ticks_since_warmup / ramp_up_ticks
                            soft_limit = int(HG_WARMUP_SOFT_LIMIT + up_frac * (HG_SOFT_LIMIT - HG_WARMUP_SOFT_LIMIT))
                    # No ramp-down in competition: positions carry to the next day within the
                    # round. Forced intraday exits sell into declines rather than holding for
                    # anchor reversion. End-of-round fair-value liquidation handles the close.
                    hg_ramp_ticks = 0
                else:
                    hg_ramp_ticks = 20_000
                    if ticks_to_exit <= hg_ramp_ticks:
                        ramp_frac  = max(0.0, ticks_to_exit) / hg_ramp_ticks
                        soft_limit = max(0, int(soft_limit * ramp_frac))

                soft_buy_room  = max(0, min(buy_room,  soft_limit - pos))
                soft_sell_room = max(0, min(sell_room, soft_limit + pos))

                # Gated sweeps: unclamped EMA for BOTH displacement and direction.
                # Displacement condition uses ema_unclamped (not clamped ema) so the
                # threshold isn't constrained by REGIME_CAP — at threshold=20, the cap
                # (±10) would always block the clamped condition but unclamped can fall
                # to anchor-70 in competition and still trigger cleanly.
                if ema_unclamped > HG_ANCHOR + sweep_threshold and ema_falling:
                    for bid in sorted(od.buy_orders, reverse=True):
                        if bid <= ema or soft_sell_room <= 0:
                            break
                        qty = min(od.buy_orders[bid], soft_sell_room)
                        orders.append(Order(product, bid, -qty))
                        soft_sell_room -= qty
                        sell_room      -= qty

                if ema_unclamped < HG_ANCHOR - sweep_threshold and ema_rising:
                    for ask in sorted(od.sell_orders):
                        if ask >= ema or soft_buy_room <= 0:
                            break
                        qty = min(abs(od.sell_orders[ask]), soft_buy_room)
                        orders.append(Order(product, ask, qty))
                        soft_buy_room -= qty
                        buy_room      -= qty

                # Reduce inventory when price comes back to skewed fair
                if pos < 0 and buy_room > 0 and fair_q in od.sell_orders:
                    qty = min(abs(od.sell_orders[fair_q]), -pos, buy_room)
                    if qty > 0:
                        orders.append(Order(product, fair_q, qty))
                        buy_room      -= qty
                        soft_buy_room -= qty

                if pos > 0 and sell_room > 0 and fair_q in od.buy_orders:
                    qty = min(od.buy_orders[fair_q], pos, sell_room)
                    if qty > 0:
                        orders.append(Order(product, fair_q, -qty))
                        sell_room      -= qty
                        soft_sell_room -= qty

                # Passive quotes inside the wide HG spread (15–17 shells).
                # Anchor guards ensure we never bid above or ask below fair value.
                if best_ask - best_bid > 1:
                    penny_bid = min(best_bid + 1, fair_q - 1)
                    penny_ask = max(best_ask - 1, fair_q + 1)
                    deep_bid  = penny_bid - 1
                    deep_ask  = penny_ask + 1

                    deep_buy = min(soft_buy_room, deep_cap)
                    if deep_buy > 0 and deep_bid < HG_ANCHOR:
                        orders.append(Order(product, deep_bid, deep_buy))

                    deep_sell = min(soft_sell_room, deep_cap)
                    if deep_sell > 0 and deep_ask > HG_ANCHOR:
                        orders.append(Order(product, deep_ask, -deep_sell))

                    penny_buy = min(soft_buy_room, penny_cap)
                    if penny_buy > 0 and penny_bid < HG_ANCHOR:
                        orders.append(Order(product, penny_bid, penny_buy))

                    penny_sell = min(soft_sell_room, penny_cap)
                    if penny_sell > 0 and penny_ask > HG_ANCHOR:
                        orders.append(Order(product, penny_ask, -penny_sell))

            # ── VELVETFRUIT_EXTRACT ───────────────────────────────────────────
            # Structure: HL ≈ 200–350 ticks, spread = 5 shells, std ≈ 14–17 shells.
            # Strategy: pure inventory-skewed market making. Skewed EMA fair value
            # causes us to quote tighter on the side we need to reduce. No delta
            # hedging — options manage their own exposure through their own skew.
            elif product == "VELVETFRUIT_EXTRACT":
                ema_prev = ts_state.get("vev_ema", mid)
                var_prev = ts_state.get("vev_var", 0.0)
                diff     = mid - ema_prev
                ema      = VEV_EMA_ALPHA * mid + (1.0 - VEV_EMA_ALPHA) * ema_prev
                var      = VEV_EMA_ALPHA * diff**2 + (1.0 - VEV_EMA_ALPHA) * var_prev
                ts_state["vev_ema"] = ema
                ts_state["vev_var"] = var

                std_dev = max(0.5, math.sqrt(max(0.0, var)))
                z_score = (mid - ema) / std_dev
                ts_state["vev_std"] = std_dev
                ts_state["vev_z"]   = z_score

                # Quote center = CURRENT MID (not lagging EMA).
                # EMA lags ~14 shells in a trending market (alpha=0.004, HL=173 ticks).
                # Using EMA as center causes adverse selection: our quotes fall below
                # the current market best_bid when price trends, giving free fills to takers.
                # Inventory skew around mid eliminates lag while still biasing direction.
                skew      = pos * VEV_SKEW_PER_UNIT
                fair      = mid - skew

                bid_price = max(0, math.floor(fair) - VEV_QUOTE_OFFSET)
                ask_price = math.ceil(fair) + VEV_QUOTE_OFFSET
                ask_price = max(ask_price, bid_price + 1)

                # Soft limit: stop quoting passively when inventory is large.
                # Inventory skew already makes further accumulation less attractive,
                # but the hard cap prevents runaway positions.
                soft_buy_room  = max(0, min(buy_room,  VEV_SOFT_LIMIT - pos))
                soft_sell_room = max(0, min(sell_room, VEV_SOFT_LIMIT + pos))

                # Post inside the spread (spread ≈ 5 shells; we offer ~3-shell spread).
                if best_ask - best_bid > 1:
                    if soft_buy_room > 0 and bid_price > best_bid:
                        orders.append(Order(product, bid_price,
                                            min(soft_buy_room, VEV_QUOTE_SIZE)))
                    if soft_sell_room > 0 and ask_price < best_ask:
                        orders.append(Order(product, ask_price,
                                            -min(soft_sell_room, VEV_QUOTE_SIZE)))

            # ── VEV options ───────────────────────────────────────────────────
            elif product.startswith("VEV_"):
                try:
                    K = int(product.split("_")[1])
                except ValueError:
                    result[product] = orders
                    continue

                if vev_mid is None:
                    result[product] = orders
                    continue

                if is_competition and K in COMPETITION_SKIP_STRIKES:
                    result[product] = orders
                    continue

                if K in DEAD_STRIKES:
                    if sell_room > 0 and best_ask >= 1:
                        orders.append(Order(product, best_ask, -min(sell_room, OPT_QUOTE_SIZE)))
                    result[product] = orders
                    continue

                option_sigma     = VEV_SIGMA_TABLE.get(K, SIGMA)
                lead_factor      = 0.5
                # Use previous-tick vev_z (written above in VEV block, read from ts_state)
                anticipatory_mid = vev_mid + (vev_z * lead_factor)
                option_delta     = bs_call_delta(anticipatory_mid, K, TTE_years, option_sigma)

                intrinsic = max(0.0, anticipatory_mid - K)
                bs_fair   = bs_call(anticipatory_mid, K, TTE_years, option_sigma)

                skew_factor   = 0.015
                pos_skew      = pos * skew_factor
                delta_skew_factor = 0.02
                delta_skew    = portfolio_delta * option_delta * delta_skew_factor
                skewed_fair   = bs_fair - pos_skew - delta_skew

                offset    = OPT_QUOTE_OFFSET.get(K, 2)
                bid_price = max(0, math.floor(skewed_fair) - offset)
                ask_price = math.ceil(skewed_fair) + offset
                ask_price = max(ask_price, bid_price + 1)

                soft_buy_room  = max(0, min(buy_room,  OPT_SOFT_LIMIT - pos))
                soft_sell_room = max(0, min(sell_room, OPT_SOFT_LIMIT + pos))

                is_deep_itm = option_delta >= 0.9
                if is_deep_itm:
                    for ask in sorted(od.sell_orders):
                        if ask >= intrinsic - 0.5 or soft_buy_room <= 0:
                            break
                        qty = min(abs(od.sell_orders[ask]), soft_buy_room)
                        orders.append(Order(product, ask, qty))
                        soft_buy_room -= qty
                        buy_room      -= qty

                # Fixed edge thresholds (vev_std * 0.8 ≈ 12 exceeds all ATM quote offsets,
                # blocking every passive quote for K=5000–5500)
                dynamic_pass_edge = OPT_PASSIVE_EDGE
                dynamic_agg_edge  = OPT_AGGRESSIVE_EDGE

                if soft_buy_room > 0 and bid_price >= best_ask:
                    edge = skewed_fair - best_ask
                    if edge >= dynamic_agg_edge:
                        qty = min(abs(od.sell_orders.get(best_ask, 0)), soft_buy_room, OPT_QUOTE_SIZE)
                        if qty > 0:
                            orders.append(Order(product, best_ask, qty))
                            soft_buy_room -= qty
                            buy_room      -= qty

                if soft_sell_room > 0 and ask_price <= best_bid:
                    edge = best_bid - skewed_fair
                    if edge >= dynamic_agg_edge:
                        qty = min(od.buy_orders.get(best_bid, 0), soft_sell_room, OPT_QUOTE_SIZE)
                        if qty > 0:
                            orders.append(Order(product, best_bid, -qty))
                            soft_sell_room -= qty
                            sell_room      -= qty

                if soft_buy_room > 0 and bid_price > best_bid:
                    edge = skewed_fair - bid_price
                    if edge >= dynamic_pass_edge:
                        orders.append(Order(product, bid_price, min(soft_buy_room, OPT_QUOTE_SIZE)))

                if soft_sell_room > 0 and ask_price < best_ask:
                    edge = ask_price - skewed_fair
                    if edge >= dynamic_pass_edge:
                        orders.append(Order(product, ask_price, -min(soft_sell_room, OPT_QUOTE_SIZE)))

            result[product] = orders

        ts_state["last_ts"] = ts
        return result, 0, json.dumps(ts_state)
