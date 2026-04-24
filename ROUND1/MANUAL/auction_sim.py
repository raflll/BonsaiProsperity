"""Pay-as-bid price-time-priority auction simulator for the Intarian Welcome manual.

Model: every bid (existing + mine) sweeps asks cheapest-first, bounded by the bid's
own price. Buyer pays their own limit price. Priority: price-desc, then time-asc
(existing orders are older than mine). Sellers are symmetric.
"""

DRYLAND_BIDS = [(30, 30000), (29, 5000), (28, 12000), (27, 28000)]
DRYLAND_ASKS = [(28, 40000), (31, 20000), (32, 20000), (33, 30000)]
DRYLAND_SETTLE = 30

EMBER_BIDS = [(20, 43000), (19, 17000), (18, 6000), (17, 5000),
              (16, 10000), (15, 5000), (14, 10000), (13, 7000)]
EMBER_ASKS = [(12, 20000), (13, 25000), (14, 35000), (15, 6000),
              (16, 5000), (18, 10000), (19, 12000)]
EMBER_SETTLE = 20

FEE = 0.05


def simulate(existing_bids, existing_asks, side, my_price, my_vol):
    """Returns my_fill. Pay-as-bid: buyer pays their limit; seller receives their limit."""
    if side == "BUY":
        bids = [(p, v, i) for i, (p, v) in enumerate(existing_bids)]
        bids.append((my_price, my_vol, "mine"))
        bids.sort(key=lambda x: (-x[0], 1 if x[2] == "mine" else 0))
        asks = sorted([list(a) for a in existing_asks], key=lambda a: a[0])

        my_fill = 0
        for price, vol, bid_id in bids:
            remaining = vol
            for ask in asks:
                if ask[0] > price:
                    break
                if ask[1] <= 0:
                    continue
                take = min(ask[1], remaining)
                if bid_id == "mine":
                    my_fill += take
                ask[1] -= take
                remaining -= take
                if remaining <= 0:
                    break
        return my_fill

    # SELL (symmetric — my ask is taken by existing bids starting highest)
    asks = [(p, v, i) for i, (p, v) in enumerate(existing_asks)]
    asks.append((my_price, my_vol, "mine"))
    asks.sort(key=lambda x: (x[0], 1 if x[2] == "mine" else 0))
    bids = sorted([list(b) for b in existing_bids], key=lambda b: -b[0])

    my_fill = 0
    for price, vol, ask_id in asks:
        remaining = vol
        for bid in bids:
            if bid[0] < price:
                break
            if bid[1] <= 0:
                continue
            take = min(bid[1], remaining)
            if ask_id == "mine":
                my_fill += take
            bid[1] -= take
            remaining -= take
            if remaining <= 0:
                break
    return my_fill


def pnl(existing_bids, existing_asks, settle, side, price, vol):
    fill = simulate(existing_bids, existing_asks, side, price, vol)
    if fill == 0:
        return 0.0, 0
    if side == "BUY":
        return fill * (settle - price - 2 * FEE), fill
    return fill * (price - settle - 2 * FEE), fill


def grid(existing_bids, existing_asks, settle, prices, vols):
    best = (-1e18, None, None, None, 0)
    for side in ("BUY", "SELL"):
        for p in prices:
            for v in vols:
                val, fill = pnl(existing_bids, existing_asks, settle, side, p, v)
                if val > best[0]:
                    best = (val, side, p, v, fill)
    return best


def report(name, bids, asks, settle, price_range, vol_range):
    print(f"\n==== {name}  (settle={settle}) ====")
    val, side, p, v, fill = grid(bids, asks, settle, price_range, vol_range)
    print(f"  optimum:  {side} {v} @ {p}  ->  fill={fill}  PnL={val:,.1f}")
    print(f"  scan at each bid price (BUY):")
    for p in price_range:
        best_v = 0
        best_pnl = 0.0
        best_fill = 0
        for v in vol_range:
            val, fill = pnl(bids, asks, settle, "BUY", p, v)
            if val > best_pnl:
                best_pnl = val
                best_v = v
                best_fill = fill
        print(f"    bid @ {p:<3d} -> best vol={best_v:>6d}, fill={best_fill:>6d}, PnL={best_pnl:>10,.1f}")


if __name__ == "__main__":
    dry_prices = range(24, 35)
    ember_prices = range(12, 22)
    vols = list(range(0, 150001, 500))

    report("Dryland Flax", DRYLAND_BIDS, DRYLAND_ASKS, DRYLAND_SETTLE, dry_prices, vols)
    report("Ember Mushroom", EMBER_BIDS, EMBER_ASKS, EMBER_SETTLE, ember_prices, vols)

    print("\n---- your submission: Dryland BUY 4001 @ 29, Ember BUY 19000 @ 17 ----")
    d_pnl, d_fill = pnl(DRYLAND_BIDS, DRYLAND_ASKS, DRYLAND_SETTLE, "BUY", 29, 4001)
    e_pnl, e_fill = pnl(EMBER_BIDS, EMBER_ASKS, EMBER_SETTLE, "BUY", 17, 19000)
    print(f"  Dryland fill={d_fill} PnL={d_pnl:,.1f}")
    print(f"  Ember   fill={e_fill} PnL={e_pnl:,.1f}")
    print(f"  TOTAL = {d_pnl + e_pnl:,.1f}")
