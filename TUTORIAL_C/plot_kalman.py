"""
Visualise the Kalman fair-value estimate against raw bid/ask for TOMATOES.

Run from TUTORIAL_ROUND_1/:
    python plot_kalman.py

Two panels:
  Top    — bid_1, ask_1, raw mid, Kalman price estimate
  Bottom — Kalman velocity (tick-to-tick drift in price units)
"""

import os
import sys
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# Make kalman.py importable when run from repo root
sys.path.insert(0, os.path.dirname(__file__))
from kalman import KalmanFilter  # noqa: E402

# ── Kalman parameters (mirror trader.py) ────────────────────────────────────
Q_PRICE = 1.0
Q_VEL   = 0.10
R_OBS   = 4.0

# ── Load price CSVs ──────────────────────────────────────────────────────────
base = os.path.dirname(__file__)
csvs = sorted(glob.glob(os.path.join(base, "prices_round_0_day_*.csv")))
df   = pd.concat([pd.read_csv(f, sep=";") for f in csvs], ignore_index=True)
df   = df.sort_values(["day", "timestamp"]).reset_index(drop=True)

tom = df[df["product"] == "TOMATOES"].reset_index(drop=True)

# ── Replay Kalman filter tick by tick ────────────────────────────────────────
kf = KalmanFilter(q_price=Q_PRICE, q_vel=Q_VEL, r_obs=R_OBS)

kf_price = []
kf_vel   = []

for mid in tom["mid_price"]:
    kf.update(float(mid))
    kf_price.append(kf.price)
    kf_vel.append(kf.velocity)

tom = tom.copy()
tom["kf_price"] = kf_price
tom["kf_vel"]   = kf_vel

# ── Day-boundary positions ───────────────────────────────────────────────────
day_bounds = []
for day, grp in tom.groupby("day", sort=True):
    day_bounds.append((grp.index[0], int(day)))

x = tom.index

# ── Plot ─────────────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(
    2, 1,
    figsize=(15, 8),
    sharex=True,
    gridspec_kw={"height_ratios": [3, 1]},
)
fig.suptitle("TOMATOES — Kalman Fair Value vs Raw Book", fontsize=13, fontweight="bold")

# ---- Top panel: prices -------------------------------------------------------
# Bid/ask shaded region
ax1.fill_between(
    x,
    tom["bid_price_1"],
    tom["ask_price_1"],
    color="steelblue",
    alpha=0.15,
    label="Bid–Ask spread",
    zorder=1,
)

ax1.plot(x, tom["bid_price_1"], color="steelblue", linewidth=0.6,
         alpha=0.6, label="Best bid", zorder=2)
ax1.plot(x, tom["ask_price_1"], color="salmon",    linewidth=0.6,
         alpha=0.6, label="Best ask", zorder=2)
ax1.plot(x, tom["mid_price"],   color="black",     linewidth=0.8,
         alpha=0.7, label="Mid price",  zorder=3)
ax1.plot(x, tom["kf_price"],    color="darkorange", linewidth=1.6,
         label="Kalman estimate", zorder=4)

ax1.set_ylabel("Price")
ax1.grid(True, alpha=0.25)
ax1.legend(fontsize=8, ncol=5, loc="upper right")
ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))

# Day dividers on top panel
for idx, day in day_bounds:
    ax1.axvline(idx, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax1.text(idx + 1, ax1.get_ylim()[1], f"Day {day}",
             color="gray", fontsize=8, va="top")

# ---- Bottom panel: Kalman velocity ------------------------------------------
ax2.axhline(0, color="black", linewidth=0.6, linestyle="--", alpha=0.4)
ax2.fill_between(x, tom["kf_vel"], 0,
                 where=(tom["kf_vel"] >= 0),
                 color="green", alpha=0.4, label="Upward drift")
ax2.fill_between(x, tom["kf_vel"], 0,
                 where=(tom["kf_vel"] < 0),
                 color="red", alpha=0.4, label="Downward drift")
ax2.plot(x, tom["kf_vel"], color="dimgray", linewidth=0.7, zorder=3)

ax2.set_ylabel("Velocity\n(ticks / tick)")
ax2.set_xlabel("Tick index")
ax2.grid(True, alpha=0.25)
ax2.legend(fontsize=8, ncol=2, loc="upper right")

for idx, _ in day_bounds:
    ax2.axvline(idx, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)

plt.tight_layout()
plt.show()
