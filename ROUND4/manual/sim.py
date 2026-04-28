# given parameters of the GBM
# µ = 0
# fixed annualized volatility = annual uncertainty of log returns = +-251% with a 1 std dev Confidence interval.
# there are 252 trading days in a year.
# there are 4 simulation ticks per trading day, 1008 in total. (discrete grid evolution)
# of course, log returns of the asset is the GBM in question.


# trading aether crystal meth

""" 

TRADING_DAYS_PER_YEAR = 252
STEPS_PER_DAY = 4
STEPS_PER_YEAR = TRADING_DAYS_PER_YEAR * STEPS_PER_DAY

def weeks_to_years(weeks: float) -> float:
    # 5 business days per week, annualized to 252 trading days
    return (weeks * 5) / TRADING_DAYS_PER_YEAR

def steps_for_weeks(weeks: float) -> int:
    return int(round(weeks * 5 * STEPS_PER_DAY))
    
    
"""


import csv
from enum import Enum
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
import pandas as pd

STRIKES = [35, 40, 45, 50, 60]

class OptionType(Enum):
    PUT           = "put"
    CALL          = "call"
    CHOOSER       = "chooser"
    BINARY_PUT    = "binary_put"
    KNOCKOUT_PUT  = "knockout_put"
    UNDERLYING    = "underlying"


@dataclass
class Contract:
    contract_id : str
    type        : OptionType
    strike      : Optional[float]
    barrier     : Optional[float]
    expiry_days : Optional[int]
    bid         : float
    ask         : float
    bid_size    : int
    ask_size    : int
    max_volume  : int
    binary_payout          : Optional[float]
    chooser_decision_days  : Optional[int]

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


def _load_contracts() -> List[Contract]:
    path = Path(__file__).parent / "options.csv"
    contracts = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            contracts.append(Contract(
                contract_id = row["contract_id"],
                type        = OptionType(row["type"]),
                strike      = float(row["strike"])               if row["strike"]                 else None,
                barrier     = float(row["barrier"])              if row["barrier"]                else None,
                expiry_days = int(row["expiry_days"])            if row["expiry_days"]            else None,
                bid         = float(row["bid"]),
                ask         = float(row["ask"]),
                bid_size    = int(row["bid_size"]),
                ask_size    = int(row["ask_size"]),
                max_volume  = int(row["max_volume"]),
                binary_payout         = float(row["binary_payout"])         if row["binary_payout"]         else None,
                chooser_decision_days = int(row["chooser_decision_days"])   if row["chooser_decision_days"] else None,
            ))
    return contracts


CONTRACTS : List[Contract] = _load_contracts()
CONTRACTS_BY_ID = {c.contract_id: c for c in CONTRACTS}


@dataclass
class OptionPosition:
    contract  : Contract
    side      : str       # "buy" or "sell"
    volume    : int
    price     : float     # fill price (bid if sell, ask if buy)


@dataclass
class Position:
    oPositions : List[OptionPosition] = field(default_factory=list)


# ................................................................ Sim Functions
def sim(positions : dict, N = 100):
    """mock run of prosperity test on given position"""
    pass

def pnl_from_gbm(positions : dict):
    """returns pnl of a position with respect to a random GBM"""
    pass

# .............................................................. validation ting
def verify_position(p : Position):
    pass


# ..............................................................................

VANILLA  = {OptionType.PUT, OptionType.CALL}
EXOTICS  = {OptionType.CHOOSER, OptionType.BINARY_PUT, OptionType.KNOCKOUT_PUT}

def get_contracts() -> pd.DataFrame:
    rows = []
    for c in CONTRACTS:
        rows.append({
            "contract_id"           : c.contract_id,
            "type"                  : c.type.value,
            "strike"                : c.strike,
            "barrier"               : c.barrier,
            "expiry_days"           : c.expiry_days,
            "bid"                   : c.bid,
            "ask"                   : c.ask,
            "mid"                   : c.mid,
            "max_volume"            : c.max_volume,
            "binary_payout"         : c.binary_payout,
            "chooser_decision_days" : c.chooser_decision_days,
        })
    return pd.DataFrame(rows).set_index("contract_id")


def get_puts_calls() -> pd.DataFrame:
    """Vanilla puts and calls grouped by strike, with bid/ask/mid columns for each side."""
    vanilla = [c for c in CONTRACTS if c.type in VANILLA]
    rows = {}
    for c in vanilla:
        key = (c.strike, c.expiry_days)
        rows.setdefault(key, {"strike": c.strike, "expiry_days": c.expiry_days})
        side = c.type.value   # "put" or "call"
        rows[key][f"{side}_bid"] = c.bid
        rows[key][f"{side}_ask"] = c.ask
        rows[key][f"{side}_mid"] = c.mid
        rows[key][f"{side}_id"]  = c.contract_id
    cols = ["strike", "expiry_days",
            "put_id",  "put_bid",  "put_ask",  "put_mid",
            "call_id", "call_bid", "call_ask", "call_mid"]
    df = pd.DataFrame(rows.values())
    return df.reindex(columns=[c for c in cols if c in df.columns]).sort_values(["strike", "expiry_days"]).reset_index(drop=True)


def get_exotics() -> pd.DataFrame:
    exotic = [c for c in CONTRACTS if c.type in EXOTICS]
    rows = []
    for c in exotic:
        rows.append({
            "contract_id"           : c.contract_id,
            "type"                  : c.type.value,
            "strike"                : c.strike,
            "barrier"               : c.barrier,
            "expiry_days"           : c.expiry_days,
            "bid"                   : c.bid,
            "ask"                   : c.ask,
            "mid"                   : c.mid,
            "binary_payout"         : c.binary_payout,
            "chooser_decision_days" : c.chooser_decision_days,
        })
    return pd.DataFrame(rows).set_index("contract_id")


# ..............................................................................

def flag_cp_arb(df : pd.DataFrame):
    pass


# ..............................................................................

def main():
    pass


# ..............................................................................

if __name__ == "__main__":
    main()
    