import glob
import os

import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(HERE, os.pardir, "data", "round3"))
OUT_DIR = os.path.join(HERE, "plots")
os.makedirs(OUT_DIR, exist_ok=True)

DAY_LEN = 1_000_000  # timestamp units per day


def load_prices() -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(DATA_DIR, "prices_round_3_day_*.csv")))
    frames = []
    for p in paths:
        df = pd.read_csv(p, sep=";")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    df = load_prices()
    df["global_t"] = df["day"] * DAY_LEN + df["timestamp"]
    df = df.sort_values("global_t")

    days = sorted(df["day"].unique())
    products = sorted(df["product"].dropna().unique())

    for product in products:
        sub = df[df["product"] == product]
        fig, ax = plt.subplots(figsize=(14, 5))
        for day in days:
            d = sub[sub["day"] == day]
            if d.empty:
                continue
            ax.plot(d["global_t"], d["mid_price"], label=f"day {day}", linewidth=0.8)

        for day in days[1:]:
            ax.axvline(day * DAY_LEN, color="grey", linestyle="--", alpha=0.4)

        ax.set_title(f"{product} — mid price")
        ax.set_xlabel("global timestamp (day * 1e6 + t)")
        ax.set_ylabel("mid price")
        ax.legend(loc="best", fontsize=8)
        ax.grid(alpha=0.3)

        out = os.path.join(OUT_DIR, f"{product}.png")
        fig.tight_layout()
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
