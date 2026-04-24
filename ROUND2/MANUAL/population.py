"""Mixture model for the opponent population.

Per the user's heuristic:
  60-70% play per the Nash distribution
  5-15% concentrate on the most-selected parts of Nash (peaks)
  10-15% pick randomly (uniform 0..100)
  10-15% favor "nice numbers" (human psychology)
  5-10% grief by picking extremes (very high or very low p)
"""

import numpy as np


NICE_NUMBERS_WEIGHTS = {
    #   p   weight  (relative, will be normalized)
    0: 3, 5: 2, 10: 3, 15: 1, 20: 3, 25: 4, 30: 2,
    33: 4, 34: 1, 40: 2, 50: 6, 60: 2, 66: 2, 67: 2,
    70: 2, 75: 2, 80: 2, 90: 2, 100: 3,
}


def nash_concentrators(nash_dist: np.ndarray, top_k: int = 3) -> np.ndarray:
    """Concentrator type: mass on the top-k peaks of Nash, reweighted."""
    idx = np.argsort(nash_dist)[::-1][:top_k]
    out = np.zeros(101)
    out[idx] = nash_dist[idx]
    total = out.sum()
    if total <= 0:
        out = np.zeros(101); out[int(np.argmax(nash_dist))] = 1.0
        return out
    return out / total


def uniform_random() -> np.ndarray:
    return np.ones(101) / 101


def nice_numbers() -> np.ndarray:
    out = np.zeros(101)
    for p, w in NICE_NUMBERS_WEIGHTS.items():
        out[p] = w
    out /= out.sum()
    return out


def griefers() -> np.ndarray:
    """Bimodal extremes. Give some mass to 0..5 and 85..100."""
    out = np.zeros(101)
    out[0:6] = 1.0          # low
    out[85:101] = 1.0       # high (overweight the real damage region)
    out /= out.sum()
    return out


def build_population(nash_dist: np.ndarray,
                     frac_nash: float = 0.65,
                     frac_conc: float = 0.10,
                     frac_rand: float = 0.125,
                     frac_nice: float = 0.125,
                     frac_grief: float = 0.075) -> np.ndarray:
    """Opponent mixture PMF. Fractions need not sum to exactly 1 (will renormalize)."""
    components = [
        (frac_nash,  nash_dist),
        (frac_conc,  nash_concentrators(nash_dist, top_k=3)),
        (frac_rand,  uniform_random()),
        (frac_nice,  nice_numbers()),
        (frac_grief, griefers()),
    ]
    mix = np.zeros(101)
    for w, d in components:
        mix += w * d
    mix /= mix.sum()
    return mix


def scenario_sweep(nash_dist: np.ndarray) -> list[dict]:
    """Return several population scenarios spanning the user's stated ranges."""
    scenarios = []
    for frac_nash, frac_conc, frac_rand, frac_nice, frac_grief, tag in [
        (0.70, 0.05, 0.10, 0.10, 0.05, "optimistic (more Nash, less grief)"),
        (0.65, 0.10, 0.125, 0.125, 0.075, "central"),
        (0.60, 0.15, 0.15,  0.15,  0.10,  "pessimistic (less Nash, more noise)"),
    ]:
        mix = build_population(nash_dist, frac_nash, frac_conc, frac_rand, frac_nice, frac_grief)
        scenarios.append({
            "tag": tag,
            "weights": (frac_nash, frac_conc, frac_rand, frac_nice, frac_grief),
            "dist": mix,
        })
    return scenarios


if __name__ == "__main__":
    # Dummy nash_dist centered at p=0 for smoke test.
    nash = np.zeros(101); nash[0] = 1.0
    mix = build_population(nash)
    print("Mix sample (central):")
    idx = np.argsort(mix)[::-1][:10]
    for i in idx:
        print(f"  p={int(i):3d}  mass={mix[i]*100:5.2f}%")
