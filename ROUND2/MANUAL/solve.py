"""Main driver for Round-2 manual "Invest & Expand" Nash / best-response analysis.

Flow:
  1. Compute the Pareto-dominant common-p symmetric Nash (everyone plays same p).
  2. Compute a QRE mixed distribution (several rationality levels).
  3. Build an opponent mixture per the user's population heuristic.
  4. Report our best response (r, s, p) and expected PnL for each scenario.
"""

import numpy as np

from mechanics import payoff_vector, full_allocation_from_p, speed_mult_large_pop
from nash import pareto_dominant_common_p, mixed_nash, verify_nash, summarize
from population import scenario_sweep, nice_numbers, griefers, uniform_random


def report_best_response(opp_dist: np.ndarray, tag: str) -> dict:
    U = payoff_vector(opp_dist)
    p_star = int(np.argmax(U))
    m = speed_mult_large_pop(p_star, opp_dist)
    alloc = full_allocation_from_p(p_star, m)
    print(f"\n--- Best response vs {tag} ---")
    print(f"  allocation:  r={alloc['r']:3d}  s={alloc['s']:3d}  p={alloc['p']:3d}  "
          f"(sum={alloc['r']+alloc['s']+alloc['p']})")
    print(f"  speed_mult:  {alloc['speed_mult']:.3f}")
    print(f"  gross:       {alloc['gross']:>12,.0f}")
    print(f"  used:        {alloc['used']:>12,.0f}")
    print(f"  PnL:         {alloc['pnl']:>12,.0f}")
    # Show top-3 alternative bids for robustness
    idx = np.argsort(U)[::-1][:5]
    print("  alt top-5 p (PnL):  " +
          "  ".join(f"p={int(i):3d}:{U[i]:,.0f}" for i in idx))
    return alloc


def main() -> None:
    np.set_printoptions(suppress=True, precision=4)

    # 1) Symmetric mixed Nash (the real one — equal expected payoff on support)
    print("=" * 70)
    print("1) Symmetric MIXED Nash (atomless-support derivation)")
    print("=" * 70)
    nash_pmf, c_nash, b_nash = mixed_nash(a=0)
    summarize(nash_pmf, "mixed-Nash")
    v = verify_nash(nash_pmf, atol=10.0)
    print(f"  support      : {int(v['support'].min())}..{int(v['support'].max())}  "
          f"(theoretical b={b_nash})")
    print(f"  U on support : mean={v['U_on_support_mean']:,.1f}  "
          f"std={v['U_on_support_std']:.1f}  "
          f"range=[{v['U_on_support_min']:,.1f}, {v['U_on_support_max']:,.1f}]")
    print(f"  U off-support max = {v['U_off_support_max']:,.1f}  "
          f"(should not exceed support by much)")
    print(f"  -> everyone playing mixed Nash earns ~{c_nash:,.0f} per player")

    # 2) Pareto-dominant common-p Nash (the coordination alternative)
    print("\n" + "=" * 70)
    print("2) Pareto-dominant common-p symmetric Nash")
    print("=" * 70)
    p, r, s, pnl = pareto_dominant_common_p()
    print(f"  If everyone plays p={p}, all tie at rank 1 (mult=0.9).")
    print(f"  Each player's best (r,s) = ({r},{s}).  Common PnL = {pnl:,.0f}")
    print("  Note: ANY common p is a pure Nash (all tied -> 0.9); p=0 is payoff-dominant,")
    print("        but without coordination the mixed Nash above is the natural attractor.")

    nash_for_mix = nash_pmf

    # 3) Best response under stylized opponents
    print("\n" + "=" * 70)
    print("3) Best response under stylized opponent archetypes")
    print("=" * 70)
    report_best_response(uniform_random(),        "UNIFORM random opponents")
    report_best_response(nice_numbers(),          "NICE-number opponents only")
    report_best_response(griefers(),              "GRIEFERS only (extremes)")
    everyone_zero = np.zeros(101); everyone_zero[0] = 1.0
    report_best_response(everyone_zero,           "everyone plays p=0")
    everyone_high = np.zeros(101); everyone_high[80] = 1.0
    report_best_response(everyone_high,           "everyone plays p=80")

    # 4) Population-mixture scenarios
    print("\n" + "=" * 70)
    print("4) Population mixture best response (user's heuristic)")
    print("=" * 70)
    print("  Using the mixed Nash as the 'Nash' fraction of players.\n")

    scenarios = scenario_sweep(nash_for_mix)
    for sc in scenarios:
        mix = sc["dist"]
        w = sc["weights"]
        tag = f"{sc['tag']}  (nash={w[0]:.0%} conc={w[1]:.0%} rand={w[2]:.0%} "\
              f"nice={w[3]:.0%} grief={w[4]:.0%})"
        report_best_response(mix, tag)

    # 5) Sensitivity: what if Nash fraction are p=0 loyalists instead?
    print("\n" + "=" * 70)
    print("5) Sensitivity: Nash fraction plays the Pareto-dominant p=0 instead")
    print("=" * 70)
    nash_zero = np.zeros(101); nash_zero[0] = 1.0
    scenarios_zero = scenario_sweep(nash_zero)
    for sc in scenarios_zero:
        mix = sc["dist"]
        w = sc["weights"]
        tag = f"[Nash=p0] {sc['tag']}  (nash={w[0]:.0%} conc={w[1]:.0%} rand={w[2]:.0%} "\
              f"nice={w[3]:.0%} grief={w[4]:.0%})"
        report_best_response(mix, tag)


if __name__ == "__main__":
    main()
