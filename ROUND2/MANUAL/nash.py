"""Nash solver for the speed-% contest.

Only Speed is strategic — it's rank-based across players. Research and Scale
are individual (no coupling). So the symmetric game reduces to: each player
picks a speed percent p in {0..100}. Given opponents' distribution over p,
your optimal (r, s) and resulting payoff U(p) is uniquely determined
(mechanics.best_rs_given_p_m), and you want to play argmax U(p).

Because speed is a step function of rank, this game admits many symmetric
pure Nash of the form "everyone plays the same p" for a range of common p —
all tied at rank 1, multiplier 0.9, and deviation down gets punished by the
multiplier dropping to 0.1. These Nash are Pareto-ranked (p=0-common is best
for everyone, but no individual can unilaterally reach it from a higher
common-p Nash without hurting themselves).

We therefore compute two kinds of solutions:

  1. Quantal Response Equilibrium (QRE): a smoothed fixed point where each
     player plays proportional to exp(beta * U). As beta -> inf this
     approaches a (generically mixed) Nash. Use this to get a *distribution*
     over p that reflects bounded rationality of the player pool.

  2. Pareto-dominant pure Nash: the payoff-dominant symmetric equilibrium,
     which is "everyone plays p = p*" for the p* that maximizes U when all
     opponents also play p. (For this payoff structure, p* = 0.)
"""

import numpy as np

from mechanics import payoff_vector, best_rs_given_p_m, G_TABLE


def mixed_nash(a: int = 0) -> tuple[np.ndarray, float, int]:
    """Symmetric mixed-strategy Nash of the speed contest (large-N limit).

    Derivation (atomless). Let G(p) = max_{r+s=100-p} research(r)*scale(s).
    Bidding p against distribution σ yields
        U(p, σ) = G(p) * (0.9 - 0.8 * S(p)) - 50000
    where S(p) = P_σ(X > p). For σ to be Nash, U must be constant c on the
    support [a, b], and indifference gives
        S(p) = 9/8 - 5(c + 50000) / (4 * G(p)).
    The boundary conditions S(a) = 1 and S(b) = 0 force
        G(a) = 9 * G(b),   c = 0.1 * G(a) - 50000 = 0.9 * G(b) - 50000.

    We pick bottom a (default 0, the maximum G, giving the tightest support
    and highest common payoff c), find b numerically, then derive the PMF
    from pmf[p] = S(p-1) - S(p) with S(-1) = 1.

    Returns (pmf, c, b).
    """
    Ga = G_TABLE[a]
    target_Gb = Ga / 9.0
    # Find b: largest p with G(p) >= target (G is decreasing).
    feasible = np.where(G_TABLE[a:] >= target_Gb)[0]
    b = int(feasible.max()) + a  # integer cap on support
    c = 0.1 * Ga - 50_000

    S = np.zeros(101)
    for p in range(a, b + 1):
        S[p] = 9.0 / 8.0 - (c + 50_000) / (0.8 * G_TABLE[p])
    S[:a] = 1.0  # mass below support has S = 1 (nothing below)
    S[:a + 1] = np.minimum(S[:a + 1], 1.0)
    S[b + 1:] = 0.0
    S = np.clip(S, 0.0, 1.0)

    pmf = np.zeros(101)
    S_prev = 1.0
    for p in range(101):
        pmf[p] = max(S_prev - S[p], 0.0)
        S_prev = S[p]
    pmf /= pmf.sum()
    return pmf, c, b


def verify_nash(pmf: np.ndarray, atol: float = 1.0) -> dict:
    """Check that the payoff U(p, pmf) is flat on support and lower elsewhere."""
    U = payoff_vector(pmf)
    support = np.where(pmf > 1e-6)[0]
    off = np.where(pmf <= 1e-6)[0]
    in_pay = U[support] if len(support) else np.array([0.0])
    return {
        "U": U,
        "support": support,
        "U_on_support_mean": float(in_pay.mean()),
        "U_on_support_std": float(in_pay.std()),
        "U_on_support_min": float(in_pay.min()),
        "U_on_support_max": float(in_pay.max()),
        "U_off_support_max": float(U[off].max()) if len(off) else -np.inf,
        "flat_within_atol": bool(in_pay.max() - in_pay.min() < atol),
    }


def pareto_dominant_common_p() -> tuple[int, int, int, float]:
    """Search common-p symmetric equilibria for the payoff-dominant one.

    If all N players play the same p, all tie at rank 1 -> multiplier 0.9.
    Returns (p*, r*, s*, PnL*) for the best such p.
    """
    best = (-1, -1, -1, -np.inf)
    for p in range(101):
        r, s, pnl = best_rs_given_p_m(p, 0.9)
        if pnl > best[3]:
            best = (p, r, s, pnl)
    return best


def qre(beta: float = 3e-4, T: int = 3000, damp: float = 0.1,
        tol: float = 1e-9, init: np.ndarray | None = None,
        verbose: bool = False) -> tuple[np.ndarray, np.ndarray, int]:
    """Logit QRE via damped fixed-point iteration.

    At each step: dist_new ∝ exp(beta * U(dist)); dist <- (1-damp)*dist + damp*dist_new.
    beta controls rationality sharpness. Larger beta -> more concentrated on BR.

    Returns (final dist, final U, iterations).
    """
    dist = init.copy() if init is not None else np.ones(101) / 101
    it = T
    for t in range(T):
        U = payoff_vector(dist)
        scaled = beta * (U - U.max())
        new = np.exp(scaled)
        new /= new.sum()
        mixed = (1 - damp) * dist + damp * new
        diff = float(np.abs(mixed - dist).max())
        dist = mixed
        if verbose and t % 200 == 0:
            peak = int(np.argmax(dist))
            print(f"  [qre] t={t:4d}  peak p={peak:3d}  max|Δ|={diff:.2e}  U_br={U.max():,.0f}")
        if diff < tol:
            it = t
            break
    U = payoff_vector(dist)
    return dist, U, it


def fictitious_play(T: int = 5000, step: float = 5e-3,
                    init: np.ndarray | None = None,
                    verbose: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Smoothed fictitious play. Moves the distribution toward argmax BR each step.

    Returns (final dist, time-averaged dist, last U).
    """
    dist = init.copy() if init is not None else np.ones(101) / 101
    avg = np.zeros(101)
    U = payoff_vector(dist)
    for t in range(T):
        U = payoff_vector(dist)
        p_star = int(np.argmax(U))
        br = np.zeros(101)
        br[p_star] = 1.0
        dist = (1 - step) * dist + step * br
        avg += dist
        if verbose and t % 500 == 0:
            print(f"  [fp] t={t:4d}  BR p*={p_star:3d}  U*={U[p_star]:,.0f}")
    avg /= T
    return dist, avg, U


def summarize(dist: np.ndarray, tag: str = "dist", top_k: int = 8) -> None:
    idx = np.argsort(dist)[::-1][:top_k]
    total = dist[idx].sum()
    print(f"  {tag} top-{top_k}: " +
          ", ".join(f"p={int(i)}:{dist[i]*100:.1f}%" for i in idx) +
          f"   (cum {total*100:.1f}%)")
    mean = float((np.arange(101) * dist).sum())
    print(f"  mean p = {mean:.2f}")


if __name__ == "__main__":
    print("== Symmetric MIXED Nash (atomless-support derivation) ==")
    pmf, c, b = mixed_nash(a=0)
    summarize(pmf, "mixed")
    v = verify_nash(pmf, atol=10.0)
    print(f"  support = {int(v['support'].min())}..{int(v['support'].max())}  "
          f"(theoretical b={b})")
    print(f"  U on support:  mean={v['U_on_support_mean']:,.1f}  "
          f"std={v['U_on_support_std']:.2f}  "
          f"min={v['U_on_support_min']:,.1f}  max={v['U_on_support_max']:,.1f}")
    print(f"  U off support max = {v['U_off_support_max']:,.1f}  "
          f"(should be <= support payoff = {c:,.1f})")
    print(f"  flat-within-10?  {v['flat_within_atol']}\n")

    print("== Pareto-dominant common-p Nash (all play same p) ==")
    p, r, s, pnl = pareto_dominant_common_p()
    print(f"  p*={p}  r={r}  s={s}  PnL(if everyone ties) = {pnl:,.0f}")
