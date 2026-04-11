import pandas as pd
import matplotlib.pyplot as plt
import glob
import os

# Load all price CSVs
csv_files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "prices_round_0_day_*.csv")))
dfs = [pd.read_csv(f, sep=";") for f in csv_files]
df = pd.concat(dfs, ignore_index=True)

# Sort by day then timestamp, create a continuous index
df = df.sort_values(["day", "timestamp"]).reset_index(drop=True)
tomatoes = df[df["product"] == "TOMATOES"].reset_index(drop=True)
tomatoes["spread"] = tomatoes["ask_price_1"] - tomatoes["bid_price_1"]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

# Continuous x-axis across days
x = range(len(tomatoes))
day_boundaries = []
for day, group in tomatoes.groupby("day"):
    idx = group.index
    day_boundaries.append((idx[0], day))

ax1.plot(x, tomatoes["mid_price"])
ax1.set_title("Tomatoes - Mid Price")
ax1.set_ylabel("Mid Price")
ax1.grid(True, alpha=0.3)

ax2.plot(x, tomatoes["spread"])
ax2.set_title("Tomatoes - Spread (Ask - Bid)")
ax2.set_ylabel("Spread")
ax2.set_xlabel("Time")
ax2.grid(True, alpha=0.3)

# Mark day boundaries on both axes
for ax in (ax1, ax2):
    for start_idx, day in day_boundaries:
        ax.axvline(x=start_idx, color="red", linestyle="--", alpha=0.5)
        ax.text(start_idx + 2, ax.get_ylim()[1], f"Day {day}", color="red", fontsize=9, va="top")

plt.tight_layout()
plt.show()
