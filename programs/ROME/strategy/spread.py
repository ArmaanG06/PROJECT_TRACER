"""The spread between the two legs of a pair.

Pure functions. Called from runner.step(); this file does not import formation or any
other pipeline stage. The runner passes in beta and alpha:
    - for a NEW entry: the beta/alpha from this month's formation
    - for an OPEN trade: the FROZEN beta/alpha saved in state at entry
"""
import numpy as np
import pandas as pd


def calc_spread(log_a: pd.Series, log_b: pd.Series, beta: float, alpha: float) -> pd.Series:
    """spread = log_a - alpha - beta * log_b

    Inputs are LOG prices on the same dates.
    No trend term here: the drift is removed once, in zscore.py (see CLAUDE.md, drift-lag bias).
    """
    pass


def pair_spread(prices: pd.DataFrame, a: str, b: str, beta: float, alpha: float) -> pd.Series:
    """Spread for one pair straight from the wide price frame.

    1. take columns a and b from prices (adj_close, NOT logged yet)
    2. keep only the dates where both legs have a price
    3. take the log of both
    4. return calc_spread(...)
    """
    pass
