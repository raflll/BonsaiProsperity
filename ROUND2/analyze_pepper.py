"""Inspect pepper root for regime structure beyond the constant 0.001 drift."""
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data", "round2")
OUT_DIR = os.path.join(HERE, "vis", "plots")
os.makedirs(OUT_DIR, exist_ok=True)

DAY_LEN = 1_000_000


def load() -> pd.DataFrame:
    frames = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "prices_round_2_day_*.csv"))):
        frames.append(pd.read_csv(p, sep=";"))
    df = pd.concat(frames, ignore_index=True)
    df = df[df["product"] == "INTARIAN_PEPPER_ROOT"].copy()
    # Some rows report mid_price=0 when one side of the book is missing —
    # those aren't real prices. Filter them out.
    df = df[df["mid_price"] > 1000].copy()
    df["global_t"] = df["day"] * DAY_LEN + df["timestamp"]
    return df.sort_values("global_t").reset_index(drop=True)


def per_day_linear(df: pd.DataFrame) -> None:
    print("\n=== per-day linear fit on mid_price ===")
    for day, g in df.groupby("day"):
        t = g["timestamp"].values
        m = g["mid_price"].values
        slope, intercept = np.polyfit(t, m, 1)
        resid = m - (slope * t + intercept)
        print(f"day {day:>3}: slope={slope:.6f}  intercept={intercept:.2f}  "
              f"resid_std={resid.std():.2f}  mid_range=[{m.min():.1f}, {m.max():.1f}]")


def residual_autocorr(df: pd.DataFrame) -> None:
    print("\n=== residual autocorrelation (mid − per-day linear fit) ===")
    resids = []
    for _, g in df.groupby("day"):
        t = g["timestamp"].values
        m = g["mid_price"].values
        slope, intercept = np.polyfit(t, m, 1)
        resids.append(m - (slope * t + intercept))
    r = np.concatenate(resids)
    r = r - r.mean()
    for lag in [1, 5, 10, 50, 100, 500, 1000]:
        if lag >= len(r):
            break
        a = r[:-lag]
        b = r[lag:]
        denom = np.sqrt((a * a).mean() * (b * b).mean())
        corr = (a * b).mean() / denom if denom else float("nan")
        print(f"  lag {lag:>4}: autocorr={corr:+.4f}")


def regime_stats(df: pd.DataFrame) -> None:
    print("\n=== residuals above/below zero — mean reversion check ===")
    for day, g in df.groupby("day"):
        t = g["timestamp"].values
        m = g["mid_price"].values
        slope, intercept = np.polyfit(t, m, 1)
        r = m - (slope * t + intercept)
        above = r > 0
        pct_above = above.mean() * 100
        # Longest continuous run above/below.
        run = 0
        max_above = max_below = 0
        prev = above[0]
        for x in above:
            if x == prev:
                run += 1
            else:
                run = 1
            if x:
                max_above = max(max_above, run)
            else:
                max_below = max(max_below, run)
            prev = x
        print(f"day {day:>3}: %above={pct_above:>5.1f}%  "
              f"longest_above_run={max_above}  longest_below_run={max_below}  "
              f"max|resid|={np.max(np.abs(r)):.1f}")


def intraday_slope(df: pd.DataFrame) -> None:
    print("\n=== slope by intraday quartile (does drift change within a day?) ===")
    for day, g in df.groupby("day"):
        t = g["timestamp"].values
        m = g["mid_price"].values
        q = np.linspace(0, len(t), 5).astype(int)
        parts = []
        for i in range(4):
            ts = t[q[i]:q[i+1]]
            ms = m[q[i]:q[i+1]]
            s, _ = np.polyfit(ts, ms, 1)
            parts.append(s)
        print(f"day {day:>3}: " + "  ".join(f"Q{i+1}={s:+.6f}" for i, s in enumerate(parts)))


def plot_residuals(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(len(df["day"].unique()), 1, figsize=(14, 9), sharex=False)
    for ax, (day, g) in zip(axes, df.groupby("day")):
        t = g["timestamp"].values
        m = g["mid_price"].values
        slope, intercept = np.polyfit(t, m, 1)
        r = m - (slope * t + intercept)
        ax.plot(t, r, linewidth=0.5)
        ax.axhline(0, color="grey", linestyle="--", alpha=0.5)
        ax.set_title(f"day {day} — residual from linear fit (slope={slope:.5f})")
        ax.set_ylabel("residual")
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("timestamp within day")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "INTARIAN_PEPPER_ROOT_residuals.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"\nwrote {out}")


def plot_rolling_slope(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(len(df["day"].unique()), 1, figsize=(14, 9), sharex=False)
    WIN = 500  # rolling window in ticks / observations
    for ax, (day, g) in zip(axes, df.groupby("day")):
        t = g["timestamp"].values
        m = g["mid_price"].values
        # Rolling slope via closed-form lstsq on windows.
        slopes = np.full(len(t), np.nan)
        for i in range(WIN, len(t)):
            ts = t[i - WIN:i]
            ms = m[i - WIN:i]
            s, _ = np.polyfit(ts, ms, 1)
            slopes[i] = s
        ax.plot(t, slopes, linewidth=0.7)
        ax.axhline(0.001, color="red", linestyle="--", alpha=0.5, label="assumed slope 0.001")
        ax.set_title(f"day {day} — rolling {WIN}-obs slope")
        ax.set_ylabel("slope")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    axes[-1].set_xlabel("timestamp within day")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "INTARIAN_PEPPER_ROOT_rolling_slope.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> None:
    df = load()
    print(f"loaded {len(df):,} rows across {df['day'].nunique()} days")
    per_day_linear(df)
    residual_autocorr(df)
    regime_stats(df)
    intraday_slope(df)
    plot_residuals(df)
    plot_rolling_slope(df)


if __name__ == "__main__":
    main()
