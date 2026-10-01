"""Every data-only class in ROME lives here: one place to look, imported wherever it's needed.

Data-only = it holds values and has no behaviour. Classes WITH behaviour (e.g. the brokers)
stay in their own files. Because these sit outside every pipeline stage, any stage can import
them without importing another stage (formation, state_mgmt and the runner all use PairSpec).
"""
from dataclasses import dataclass
from typing import NamedTuple

import pandas as pd


# ---- stats.py results -----------------------------------------------------
@dataclass(frozen=True)
class HedgeFit:
    beta: float
    alpha: float
    trend: float
    resid: pd.Series

@dataclass(frozenn=True)
class CointResult:
    tstat: float
    pvalue: float
    crit: dict


# ---- formation.py result ----------------------------------------------------

@dataclass(frozen=True)
class PairSpec:
    pair_id: str            # "A-B"
    a: str                  # dependent leg (coint_direction: a_on_b)
    b: str
    beta: float
    alpha: float
    trend: float
    half_life: float        # trading days
    sigma: float            # std of the detrended residual (log units)
    pvalue: float
    status: str             # tradable | no_data | negative_beta | not_cointegrated | half_life | cost
    reason: str
    selected: bool          # tradable AND inside top_n
    formed_on: pd.Timestamp


# ---- still to come ----------------------------------------------------------
# State (state_mgmt.py): pair ID, direction, frozen entry beta/alpha, entry date, entry half-life,
#                        Kalman beta/alpha/P, breakdown fail count, exit-only flag
