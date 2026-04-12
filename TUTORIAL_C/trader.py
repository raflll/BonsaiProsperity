import json
from datamodel import OrderDepth, TradingState, Order
from typing import List, TypedDict


# ============================================================
# Source of truth is kalman.py; keep them in sync.
# ============================================================
class KalmanFilter:
    """Two-state Kalman filter: tracks [price, velocity]."""

    def __init__(
        self,
        q_price: float = 1.0,
        q_vel: float = 0.1,
        r_obs: float = 2.0,
        init_price: float | None = None,
        init_uncertainty: float = 1000.0,
    ):
        self.q_price = q_price
        self.q_vel = q_vel
        self.r_obs = r_obs
        self.x: list[float] | None = [init_price, 0.0] if init_price is not None else None
        self.P: list[float] | None = (
            [init_uncertainty, 0.0, 0.0, init_uncertainty * 0.01]
            if init_price is not None else None
        )

    def update(self, obs: float) -> float:
        if self.x is None:
            self.x = [obs, 0.0]
            self.P = [1000.0, 0.0, 0.0, 10.0]
            return obs
        x_pred, P_pred = self._predict()
        self.x, self.P = self._update(x_pred, P_pred, obs)
        return self.x[0]

    @property
    def price(self) -> float | None:
        return self.x[0] if self.x is not None else None

    def to_dict(self) -> dict:
        return {"x": self.x, "P": self.P,
                "q_price": self.q_price, "q_vel": self.q_vel, "r_obs": self.r_obs}

    @classmethod
    def from_dict(cls, d: dict) -> "KalmanFilter":
        kf = cls(q_price=d["q_price"], q_vel=d["q_vel"], r_obs=d["r_obs"])
        kf.x = d["x"]
        kf.P = d["P"]
        return kf

    def _predict(self) -> tuple[list[float], list[float]]:
        assert self.x is not None and self.P is not None
        p, v = self.x
        P = self.P
        fp = [P[0] + P[2], P[1] + P[3], P[2], P[3]]
        fPfT = [fp[0] + fp[1], fp[1], fp[2] + fp[3], fp[3]]
        P_pred = [fPfT[0] + self.q_price, fPfT[1], fPfT[2], fPfT[3] + self.q_vel]
        return [p + v, v], P_pred

    def _update(self, x_pred: list[float], P_pred: list[float], obs: float) -> tuple[list[float], list[float]]:
        innov = obs - x_pred[0]
        S = P_pred[0] + self.r_obs
        K0, K1 = P_pred[0] / S, P_pred[2] / S
        x_upd = [x_pred[0] + K0 * innov, x_pred[1] + K1 * innov]
        P_upd = [
            (1 - K0) * P_pred[0],           (1 - K0) * P_pred[1],
            -K1 * P_pred[0] + P_pred[2],    -K1 * P_pred[1] + P_pred[3],
        ]
        return x_upd, P_upd
# ============================================================


class _KP(TypedDict):
    q_price: float
    q_vel: float
    r_obs: float
    init_price: float | None

# ======================== TUNABLE PARAMETERS ========================
# Kalman noise params per product.

KALMAN_PARAMS: dict[str, _KP] = {
    "EMERALDS": {"q_price": 0.05, "q_vel": 0.001, "r_obs": 1.0, "init_price": 10000.0},
    "TOMATOES": {"q_price": 1.0,  "q_vel": 0.10,  "r_obs": 4.0, "init_price": None},
}

POSITION_LIMITS = {
    "EMERALDS": 50,
    "TOMATOES": 50,
}

QUOTE_SPREAD = {   # half-spread for passive quotes (ticks)
    "EMERALDS": 1,
    "TOMATOES": 2,
}
# ====================================================================


class Trader:

    def run(self, state: TradingState):
        # ---- Load persistent Kalman state ----
        raw = getattr(state, "traderData", "") or ""
        saved: dict = json.loads(raw) if raw else {}

        result = {}
        kf_states_out = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            if not order_depth.buy_orders or not order_depth.sell_orders:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid = (best_bid + best_ask) / 2.0
            pos = state.position.get(product, 0)
            limit = POSITION_LIMITS.get(product, 50)

            # ---- Restore or initialise Kalman filter for this product ----
            kp = KALMAN_PARAMS.get(product)
            if kp is None:
                # Unknown product — skip
                result[product] = []
                continue

            if product in saved:
                kf = KalmanFilter.from_dict(saved[product])
            else:
                ip = kp["init_price"]
                kf = KalmanFilter(
                    q_price=float(kp["q_price"]),
                    q_vel=float(kp["q_vel"]),
                    r_obs=float(kp["r_obs"]),
                    init_price=float(ip) if ip is not None else None,
                )

            # Feed mid-price into the filter — get posterior fair-value estimate
            fair = kf.update(mid)

            # ---- TAKE: lift/hit orders that cross the Kalman fair value ----
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if ask_price >= fair or pos >= limit:
                    break
                qty = min(-order_depth.sell_orders[ask_price], limit - pos)
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    pos += qty

            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                if bid_price <= fair or pos <= -limit:
                    break
                qty = min(order_depth.buy_orders[bid_price], limit + pos)
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty))
                    pos -= qty

            # ---- MAKE: penny the current book, clamped to not cross fair ----
            half = QUOTE_SPREAD.get(product, 1)
            penny_bid = best_bid + 1
            penny_ask = best_ask - 1

            fair_int = int(fair)
            if penny_bid >= fair_int:
                penny_bid = fair_int - half
            if penny_ask <= fair_int:
                penny_ask = fair_int + half
            if penny_bid >= penny_ask:
                penny_bid = fair_int - half
                penny_ask = fair_int + half

            buy_room  = limit - pos
            sell_room = limit + pos

            if buy_room > 0:
                orders.append(Order(product, penny_bid, buy_room))
            if sell_room > 0:
                orders.append(Order(product, penny_ask, -sell_room))

            result[product] = orders
            kf_states_out[product] = kf.to_dict()

        traderData = json.dumps(kf_states_out)
        conversions = 0
        return result, conversions, traderData
