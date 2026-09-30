"""Pair statistics shared by formation and the engine.

Every function is pure: it sees only the window it is given, so look-ahead is the
caller's job (the runner hands in data <= t). Inputs are LOG total-return-adjusted
prices as pandas Series on a shared date index.
"""
from typing import NamedTuple

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint


class HedgeFit(NamedTuple):
    beta: float          # units of log(b) per unit of log(a)
    alpha: float         # intercept
    trend: float         # slope per observation (0.0 when trend="c")
    resid: pd.Series     # detrended residual: log_a - alpha - trend*t - beta*log_b


class CointResult(NamedTuple):
    tstat: float
    pvalue: float        # MacKinnon
    crit: dict           # {"1%": .., "5%": .., "10%": ..}


def _align(log_a: pd.Series, log_b: pd.Series) -> tuple[pd.Series, pd.Series]:
    df = pd.concat([log_a, log_b], axis=1, join="inner")
    if df.isna().any().any():
        raise ValueError("NaNs in the price window; clean the data before testing")
    return df.iloc[:, 0], df.iloc[:, 1]


def hedge_ratio(log_a: pd.Series, log_b: pd.Series, trend: str = "ct") -> HedgeFit:
    """OLS of log_a on log_b, with a constant ("c") or constant + time trend ("ct").

    Leg a is the dependent variable. Use the same trend as cointegration() so the
    beta you trade is the beta you tested.
    """
    if trend not in ("c", "ct"):
        raise ValueError(f"trend must be 'c' or 'ct', got {trend!r}")
    a, b = _align(log_a, log_b)

    X = pd.DataFrame({"const": 1.0, "b": b}, index=b.index)
    if trend == "ct":
        X["t"] = np.arange(len(b), dtype=float)
    fit = sm.OLS(a, X).fit()

    return HedgeFit(
        beta=float(fit.params["b"]),
        alpha=float(fit.params["const"]),
        trend=float(fit.params.get("t", 0.0)),
        resid=fit.resid,
    )


def cointegration(log_a: pd.Series, log_b: pd.Series, trend: str = "ct",
                  autolag: str = "aic") -> CointResult:
    """Engle-Granger test on the OLS residuals, MacKinnon p-values.

    Never pass Kalman residuals here: the filter absorbs the non-stationarity and
    everything looks cointegrated.
    """
    a, b = _align(log_a, log_b)
    tstat, pvalue, crit = coint(a, b, trend=trend, autolag=autolag)
    return CointResult(
        tstat=float(tstat),
        pvalue=float(pvalue),
        crit={"1%": float(crit[0]), "5%": float(crit[1]), "10%": float(crit[2])},
    )


def half_life(resid: pd.Series) -> float:
    """Mean-reversion half-life in observations (trading days) from an AR(1) fit.

    Pass the DETRENDED residual (HedgeFit.resid). Returns inf if the series does
    not mean-revert (phi >= 1) or oscillates (phi <= 0).
    """
    x = resid.dropna()
    lagged = x.shift(1).iloc[1:]
    current = x.iloc[1:]

    fit = sm.OLS(current, sm.add_constant(lagged)).fit()
    phi = float(fit.params.iloc[1])

    if phi <= 0 or phi >= 1:
        return float("inf")
    return float(-np.log(2) / np.log(phi))
