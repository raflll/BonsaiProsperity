import json
from typing import Any, List

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, List[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self._to_json(
                [
                    self._compress_state(state, ""),
                    self._compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self._to_json(
                [
                    self._compress_state(state, self._truncate(state.traderData, max_item_length)),
                    self._compress_orders(orders),
                    conversions,
                    self._truncate(trader_data, max_item_length),
                    self._truncate(self.logs, max_item_length),
                ]
            )
        )
        self.logs = ""

    def _compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self._compress_listings(state.listings),
            self._compress_order_depths(state.order_depths),
            self._compress_trades(state.own_trades),
            self._compress_trades(state.market_trades),
            state.position,
            self._compress_observations(state.observations),
        ]

    def _compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        return [[l.symbol, l.product, l.denomination] for l in listings.values()]

    def _compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        return {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()}

    def _compress_trades(self, trades: dict[Symbol, List[Trade]]) -> list[list[Any]]:
        out: list[list[Any]] = []
        for arr in trades.values():
            for t in arr:
                out.append([t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp])
        return out

    def _compress_observations(self, observations: Observation) -> list[Any]:
        plain = getattr(observations, "plainValueObservations", {})
        conv = getattr(observations, "conversionObservations", {})
        conv_compressed = {}
        for product, obs in conv.items():
            conv_compressed[product] = [
                getattr(obs, "bidPrice", None),
                getattr(obs, "askPrice", None),
                getattr(obs, "transportFees", None),
                getattr(obs, "exportTariff", None),
                getattr(obs, "importTariff", None),
                getattr(obs, "sunlight", None),
                getattr(obs, "humidity", None),
            ]
        return [plain, conv_compressed]

    def _compress_orders(self, orders: dict[Symbol, List[Order]]) -> list[list[Any]]:
        out: list[list[Any]] = []
        for arr in orders.values():
            for o in arr:
                out.append([o.symbol, o.price, o.quantity])
        return out

    def _to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def _truncate(self, value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value
        return value[: max_length - 3] + "..."


logger = Logger()


FIXED_FAIR = {
    "ASH_COATED_OSMIUM": 10000,
}

EMA_ALPHA = {
    "INTARIAN_PEPPER_ROOT": 0.1,
}

POSITION_LIMITS = {
    "ASH_COATED_OSMIUM": 50,
    "INTARIAN_PEPPER_ROOT": 50,
}

TRADED_PRODUCTS = set(FIXED_FAIR.keys()) | set(EMA_ALPHA.keys())


def compute_fair(product: str, order_depth: OrderDepth, ema_state: dict) -> float | None:
    if product in FIXED_FAIR:
        return float(FIXED_FAIR[product])

    if product in EMA_ALPHA:
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        mid = (best_bid + best_ask) / 2.0
        prev = ema_state.get(product)
        if prev is None:
            new = mid
        else:
            a = EMA_ALPHA[product]
            new = a * mid + (1 - a) * prev
        ema_state[product] = new
        return new

    return None


class Trader:

    def run(self, state: TradingState):
        try:
            ema_state = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            ema_state = {}

        result: dict[Symbol, List[Order]] = {}

        for product in state.order_depths:
            if product not in TRADED_PRODUCTS:
                continue

            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            pos = state.position.get(product, 0)
            limit = POSITION_LIMITS[product]

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            fair = compute_fair(product, order_depth, ema_state)
            if fair is None:
                result[product] = []
                continue

            logger.print(f"{product} pos={pos} bb={best_bid} ba={best_ask} fair={fair:.2f}")

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

            penny_bid = best_bid + 1
            penny_ask = best_ask - 1

            fair_floor = int(fair)
            fair_ceil = fair_floor + 1 if fair > fair_floor else fair_floor

            if penny_bid >= fair:
                penny_bid = fair_floor - 1
            if penny_ask <= fair:
                penny_ask = fair_ceil + 1

            if penny_bid >= penny_ask:
                penny_bid = fair_floor - 1
                penny_ask = fair_ceil + 1

            buy_room = limit - pos
            sell_room = limit + pos

            if buy_room > 0:
                lvl1 = buy_room // 2
                lvl2 = buy_room - lvl1
                if lvl1 > 0:
                    orders.append(Order(product, penny_bid, lvl1))
                if lvl2 > 0:
                    orders.append(Order(product, penny_bid - 1, lvl2))
            if sell_room > 0:
                lvl1 = sell_room // 2
                lvl2 = sell_room - lvl1
                if lvl1 > 0:
                    orders.append(Order(product, penny_ask, -lvl1))
                if lvl2 > 0:
                    orders.append(Order(product, penny_ask + 1, -lvl2))

            result[product] = orders

        conversions = 0
        trader_data = json.dumps(ema_state)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data