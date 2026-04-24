"""Round 2 manual challenge "Invest & Expand" — payoff primitives.

Rules:
  - Budget: 50,000 XIRECs.
  - Allocate integer percents r, s, p (Research, Scale, Speed) with r+s+p <= 100.
  - research(r)  = 200_000 * ln(1+r) / ln(101)     # logarithmic, 0 -> 0, 100 -> 200k
  - scale(s)     = 7 * s / 100                     # linear, 0 -> 0, 100 -> 7
  - speed(p)     = rank-based across ALL players, 0.1..0.9 linearly by rank
                   (ties share the lowest rank of their tie group)
  - PnL = research(r) * scale(s) * speed(p) - 500 * (r+s+p)
"""

import numpy as np

BUDGET = 50_000
COST_PER_PCT = BUDGET / 100   # 500 XIRECs per percent used
LN101 = np.log(101)
SPEED_LO = 0.1
SPEED_HI = 0.9

PCT = np.arange(0, 101)
RESEARCH = 200_000 * np.log(1 + PCT) / LN101          # length 101
SCALE = 7 * PCT / 100


def speed_mult_from_ranks(investments: np.ndarray) -> np.ndarray:
    """Rank-based multiplier for an array of speed investments.

    Ties share the lowest rank of their tie group (matches rules example:
    70,70,70,50,40,40,30 -> 1,1,1,4,5,5,7).
    Multiplier is linearly scaled from 0.9 (rank 1) to 0.1 (rank N).
    """
    N = len(investments)
    if N == 1:
        return np.array([SPEED_HI])
    inv = np.asarray(investments)
    # rank_i = 1 + (# strictly greater)
    rank = 1 + (inv[:, None] < inv[None, :]).sum(axis=1)
    return SPEED_HI - (SPEED_HI - SPEED_LO) * (rank - 1) / (N - 1)


def speed_mult_large_pop(p: int, opp_dist: np.ndarray) -> float:
    """Large-population-limit multiplier for bidding p against opp distribution.

    opp_dist is a length-101 pmf over integer speed %s for the opponents.
    With ties sharing the lowest rank of their tie group, the fraction of
    players strictly greater than you determines your rank fraction.
    """
    if p >= 100:
        return SPEED_HI
    greater_mass = float(opp_dist[p + 1:].sum())
    return SPEED_HI - (SPEED_HI - SPEED_LO) * greater_mass


def best_rs_given_p_m(p: int, m: float) -> tuple[int, int, float]:
    """Optimal integer (r, s) with r+s <= 100-p, for given speed multiplier m.

    Returns (r*, s*, pnl*). Scale is linear in s, so if marginal of s is
    positive we push s to the cap (100-p-r); otherwise we scan the corner.
    For robustness we scan r in [0, 100-p] with s = 100-p-r (full use) AND
    compare against the no-op (r=s=0) baseline.
    """
    B = 100 - p
    if B <= 0:
        return 0, 0, -COST_PER_PCT * p

    rs = np.arange(0, B + 1)
    ss = B - rs
    gross = RESEARCH[rs] * SCALE[ss] * m
    used_full = COST_PER_PCT * 100           # (r+s+p) = 100 when s=B-r
    pnl_full = gross - used_full

    # No-op alternative: r=s=0, only pay for p.
    pnl_noop = -COST_PER_PCT * p

    i = int(np.argmax(pnl_full))
    if pnl_full[i] >= pnl_noop:
        return int(rs[i]), int(ss[i]), float(pnl_full[i])
    return 0, 0, float(pnl_noop)


def G_of_p(p: int) -> float:
    """Max research(r) * scale(s) over r + s <= 100-p (no m factor).

    Scale is linear in s, so if research(r) > 0 the optimal is s = 100-p-r
    (push s to the cap). Scan r to find the best.
    """
    B = 100 - p
    if B <= 0:
        return 0.0
    rs = np.arange(0, B + 1)
    ss = B - rs
    vals = RESEARCH[rs] * SCALE[ss]
    return float(vals.max())


G_TABLE = np.array([G_of_p(p) for p in range(101)])


def payoff_vector(opp_dist: np.ndarray) -> np.ndarray:
    """Expected PnL of bidding each p in 0..100 (with best r,s) vs opp_dist."""
    U = np.empty(101)
    for p in range(101):
        m = speed_mult_large_pop(p, opp_dist)
        _, _, pnl = best_rs_given_p_m(p, m)
        U[p] = pnl
    return U


def full_allocation_from_p(p: int, m: float) -> dict:
    r, s, pnl = best_rs_given_p_m(p, m)
    return {
        "r": r, "s": s, "p": p,
        "research_val": float(RESEARCH[r]),
        "scale_val": float(SCALE[s]),
        "speed_mult": float(m),
        "gross": float(RESEARCH[r] * SCALE[s] * m),
        "used": float(COST_PER_PCT * (r + s + p)),
        "pnl": float(pnl),
    }


if __name__ == "__main__":
    # Sanity: p=0, m=0.9 -> best r,s.
    r, s, pnl = best_rs_given_p_m(0, 0.9)
    print(f"p=0, m=0.9 -> r={r}, s={s}, PnL={pnl:,.0f}")
    # Reproduce rule example ranks:
    ex = np.array([70, 70, 70, 50, 40, 40, 30])
    print("ranks example ->", speed_mult_from_ranks(ex).round(3))
    ex2 = np.array([95, 20, 10])
    print("three-player example ->", speed_mult_from_ranks(ex2).round(3))
