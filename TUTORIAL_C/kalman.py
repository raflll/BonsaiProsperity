"""
Two-state Kalman filter for fair-value estimation.

State vector:  x = [price, velocity]
  price     — the latent true fair value
  velocity  — tick-to-tick drift (trend component)

Process model  (constant-velocity random walk):
  price_{t+1}    = price_t + velocity_t  +  w_price
  velocity_{t+1} = velocity_t            +  w_vel
  → F = [[1, 1],
         [0, 1]]

Observation model (mid-price is a noisy measurement of price):
  z_t = price_t + v,   v ~ N(0, R)
  → H = [1, 0]

Noise parameters
----------------
q_price : float
    Process noise on the price level per tick.  Higher = filter trusts
    observations more and tracks price moves faster.
q_vel : float
    Process noise on the velocity per tick.  Higher = trend can reverse
    faster.  Keep this much smaller than q_price so velocity is stable.
r_obs : float
    Observation noise variance.  Should be ~ (half_spread)^2 or estimated
    from the typical noise in the mid-price series.
"""


class KalmanFilter:
    """
    Pure-Python 2-state Kalman filter (no numpy).

    State x = [price, velocity] stored as a plain list.
    Covariance P is a 2×2 matrix stored as a flat 4-list
    in row-major order: [P00, P01, P10, P11].
    """

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

        # State and covariance — None until first observation
        self.x: list[float] | None = [init_price, 0.0] if init_price is not None else None
        # Large off-diagonal uncertainty on first initialisation
        self.P: list[float] | None = (
            [init_uncertainty, 0.0, 0.0, init_uncertainty * 0.01]
            if init_price is not None
            else None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, obs: float) -> float:
        """
        Incorporate one new mid-price observation.
        Returns the posterior price estimate (filtered fair value).
        """
        if self.x is None:
            # Cold start: seed state from first observation
            self.x = [obs, 0.0]
            self.P = [1000.0, 0.0, 0.0, 10.0]
            return obs

        x_pred, P_pred = self._predict()
        self.x, self.P = self._update(x_pred, P_pred, obs)
        return self.x[0]

    @property
    def price(self) -> float | None:
        """Current price estimate."""
        return self.x[0] if self.x is not None else None

    @property
    def velocity(self) -> float:
        """Current velocity (drift per tick)."""
        return self.x[1] if self.x is not None else 0.0

    # ------------------------------------------------------------------
    # Serialisation — persists across ticks via traderData JSON
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "P": self.P,
            "q_price": self.q_price,
            "q_vel": self.q_vel,
            "r_obs": self.r_obs,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KalmanFilter":
        kf = cls(
            q_price=d["q_price"],
            q_vel=d["q_vel"],
            r_obs=d["r_obs"],
        )
        kf.x = d["x"]
        kf.P = d["P"]
        return kf

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _predict(self) -> tuple[list[float], list[float]]:
        """
        Predict step.

        F = [[1, 1],
             [0, 1]]

        x_pred = F @ x
        P_pred = F @ P @ F^T + Q
        """
        assert self.x is not None and self.P is not None
        p, v = self.x
        P = self.P  # [P00, P01, P10, P11]

        # x_pred
        x_pred = [p + v, v]

        # F @ P  (where F = [[1,1],[0,1]])
        fp = [
            P[0] + P[2],  P[1] + P[3],   # row 0: F[0]·P cols
            P[2],          P[3],            # row 1: F[1]·P cols
        ]

        # (F @ P) @ F^T  (F^T = [[1,0],[1,1]])
        fPfT = [
            fp[0] + fp[1],  fp[1],          # row 0
            fp[2] + fp[3],  fp[3],           # row 1
        ]

        # + Q = diag(q_price, q_vel)
        P_pred = [
            fPfT[0] + self.q_price,  fPfT[1],
            fPfT[2],                  fPfT[3] + self.q_vel,
        ]

        return x_pred, P_pred

    def _update(
        self,
        x_pred: list[float],
        P_pred: list[float],
        obs: float,
    ) -> tuple[list[float], list[float]]:
        """
        Update step.

        H = [1, 0]  →  only price is observed.

        Innovation:   y  = obs  - H @ x_pred  = obs - p_pred
        Innovation cov: S = H @ P_pred @ H^T + R = P_pred[0,0] + R
        Kalman gain:  K  = P_pred @ H^T / S
                         = [P_pred[0,0], P_pred[2,0]]^T / S
        Posterior:    x  = x_pred + K * y
                      P  = (I - K @ H) @ P_pred
        """
        p_pred = x_pred[0]

        # Innovation and its variance
        innov = obs - p_pred
        S = P_pred[0] + self.r_obs          # scalar

        # Kalman gain (2×1 vector)
        K0 = P_pred[0] / S                  # gain on price state
        K1 = P_pred[2] / S                  # gain on velocity state

        # Posterior state
        x_upd = [x_pred[0] + K0 * innov, x_pred[1] + K1 * innov]

        # Posterior covariance  P = (I - K@H) @ P_pred
        # I - K@H = [[1-K0, 0], [-K1, 1]]
        P_upd = [
            (1 - K0) * P_pred[0],               (1 - K0) * P_pred[1],
            -K1 * P_pred[0] + P_pred[2],         -K1 * P_pred[1] + P_pred[3],
        ]

        return x_upd, P_upd
