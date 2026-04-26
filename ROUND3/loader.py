"""
Central data access for Round 3.

Quick reference:
    load_prices()                   -> full raw prices DataFrame
    load_trades()                   -> full raw trades DataFrame
    price_history(product)          -> mid_price time series for any product
    trade_history(product)          -> trade records for any product
    spot()                          -> VELVETFRUIT_EXTRACT price series (VEV underlying)
    options_prices()                -> all VEV options with strike, T, spot, moneyness, iv
    option_price_history(strike)    -> price time series for one VEV option
    option_trade_history(strike)    -> trades for one VEV option
"""

import glob
import os

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "round3"))
TOTAL_TIMESTAMPS = 3_000_000
TIME_TO_EXPIRY = 5_000_000


# ---------------------------------------------------------------------------
# Raw loaders   
# ---------------------------------------------------------------------------

def load_prices() -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(DATA_DIR, "prices_round_3_day_*.csv")))
    df = pd.concat([pd.read_csv(p, sep=";") for p in paths], ignore_index=True)
    df["abs_ts"] = df["day"] * 1_000_000 + df["timestamp"]
    return df


def load_trades() -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(DATA_DIR, "trades_round_3_day_*.csv")))
    frames = []
    for p in paths:
        day = int(os.path.basename(p).split("_day_")[1].split(".")[0])
        frame = pd.read_csv(p, sep=";")
        frame.insert(0, "day", day)
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    df["abs_ts"] = df["day"] * 1_000_000 + df["timestamp"]
    return df


# ---------------------------------------------------------------------------
# Product-level access
# ---------------------------------------------------------------------------

def price_history(product: str) -> pd.DataFrame:
    """Mid-price time series for any product."""
    df = load_prices()
    return (
        df[df["product"] == product][["day", "timestamp", "abs_ts", "mid_price"]]
        .reset_index(drop=True)
    )


def trade_history(product: str) -> pd.DataFrame:
    """All trades for any product (uses 'symbol' column in trades data)."""
    df = load_trades()
    return (
        df[df["symbol"] == product][["day", "timestamp", "abs_ts", "buyer", "seller", "price", "quantity"]]
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Spot (VEV underlying = VELVETFRUIT_EXTRACT)
# ---------------------------------------------------------------------------

def spot() -> pd.DataFrame:
    """VELVETFRUIT_EXTRACT price series — the VEV underlying."""
    return price_history("VELVETFRUIT_EXTRACT")


# ---------------------------------------------------------------------------
# Options helpers
# ---------------------------------------------------------------------------

def _bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return float(S * norm.cdf(d1) - K * norm.cdf(d2))


def _implied_vol(price: float, S: float, K: float, T: float) -> float:
    if T <= 0 or price <= max(S - K, 0.0):
        return np.nan
    try:
        return float(brentq(lambda sigma: _bs_call(S, K, T, sigma) - price, 1e-6, 10.0))
    except ValueError:
        return np.nan


def options_prices() -> pd.DataFrame:
    """
    All VEV option observations with derived columns:
        strike, T, spot, moneyness, iv
    T is normalised to [0, 1] over the 7-day round.
    """
    df = load_prices()

    _spot = (
        df[df["product"] == "VELVETFRUIT_EXTRACT"][["abs_ts", "mid_price"]]
        .rename(columns={"mid_price": "spot"})
    )

    opts = df[df["product"].str.startswith("VEV_")].copy()
    opts["strike"] = opts["product"].str.extract(r"VEV_(\d+)", expand=False).astype(int)
    opts["T"] = (TIME_TO_EXPIRY - opts["abs_ts"]) / TIME_TO_EXPIRY
    opts = opts.merge(_spot, on="abs_ts", how="left")
    opts["moneyness"] = opts["strike"] / opts["spot"]
    opts["iv"] = opts.apply(
        lambda r: _implied_vol(r["mid_price"], r["spot"], r["strike"], r["T"]), axis=1
    )
    return opts.reset_index(drop=True)


def option_price_history(strike: int) -> pd.DataFrame:
    """Mid-price + IV time series for a single VEV strike."""
    opts = options_prices()
    return (
        opts[opts["strike"] == strike][["day", "timestamp", "abs_ts", "mid_price", "spot", "T", "moneyness", "iv"]]
        .reset_index(drop=True)
    )


def option_trade_history(strike: int) -> pd.DataFrame:
    """All trades for a single VEV strike."""
    return trade_history(f"VEV_{strike}")
