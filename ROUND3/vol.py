import matplotlib.pyplot as plt
from ROUND3.loader import options_prices


def main() -> None:
    options = options_prices()

    strikes = sorted(options["strike"].unique())
    cmap = plt.colormaps["plasma"].resampled(len(strikes))
    color_map = {k: cmap(i) for i, k in enumerate(strikes)}

    plt.rcParams["agg.path.chunksize"] = 10000
    fig, ax = plt.subplots(figsize=(12, 6))
    for strike, grp in options.groupby("strike"):
        ax.scatter(grp["moneyness"], grp["iv"], c=[color_map[strike]], s=4, alpha=0.5, label=str(strike))
    ax.set_xlabel("Moneyness (K/S)")
    ax.set_ylabel("Implied Volatility")
    ax.set_title("VEV Vol Smile")
    ax.legend(title="Strike", markerscale=3, fontsize=8)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
