"""Monthly formation: which pairs are tradable as of refit date t.

Pure function. It sees prices <= t only, returns a PairSpec for EVERY pair (not just the
winners) so the kill/continue check can see why each pair failed. Exit-only marking of open
trades is the runner's job (state_mgmt.mark_exit_only), not formation's.
"""
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from ROME.strategy.stats import cointegration, half_life, hedge_ratio


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
    reason: str             # human-readable detail for the first filter that failed
    selected: bool          # tradable AND inside top_n
    formed_on: pd.Timestamp


def form_pairs(prices: pd.DataFrame, t, pairs: pd.DataFrame, cfg: dict) -> list[PairSpec]:
    """Test every pair on the window ending at t.

    prices: wide adj_close frame (dates x tickers), total-return adjusted, one source per symbol.
    t:      refit date. Anything after t is dropped here as a second look-ahead guard.
    pairs:  the pairs file (symbol_a, symbol_b, rationale).
    cfg:    the strategies.ROME.formation section of configs.yaml.
    """
    t = pd.Timestamp(t)
    prices = prices.loc[:t]

    specs = [_test_pair(prices, t, row.symbol_a, row.symbol_b, cfg) for row in pairs.itertuples()]
    return _select(specs, cfg["top_n"], cfg["rank_by"])


def _window(prices: pd.DataFrame, t: pd.Timestamp, months: int) -> pd.DataFrame:
    return prices.loc[(prices.index > t - pd.DateOffset(months=months)) & (prices.index <= t)]


def _test_pair(prices, t, a, b, cfg) -> PairSpec:
    def spec(status, reason, beta=np.nan, alpha=np.nan, trend=np.nan,
             hl=np.nan, sigma=np.nan, pvalue=np.nan):
        return PairSpec(f"{a}-{b}", a, b, beta, alpha, trend, hl, sigma, pvalue,
                        status, reason, False, t)

    # 1. data coverage on the longer of the two windows
    longest = _window(prices, t, max(cfg["lookback_months"], cfg["test_window_months"]))
    for leg in (a, b):
        if leg not in longest.columns or len(longest) == 0:
            return spec("no_data", f"{leg} not in price data")
        coverage = longest[leg].notna().mean()
        if coverage < cfg["min_coverage"]:
            return spec("no_data", f"{leg} coverage {coverage:.0%} < {cfg['min_coverage']:.0%}")

    # 2. log prices, both legs present on the same days
    fit_win = np.log(_window(prices, t, cfg["lookback_months"])[[a, b]].dropna())
    test_win = np.log(_window(prices, t, cfg["test_window_months"])[[a, b]].dropna())

    # 3. hedge ratio, cointegration, half-life, sigma
    fit = hedge_ratio(fit_win[a], fit_win[b], trend=cfg["coint_trend"])
    pvalue = cointegration(test_win[a], test_win[b], trend=cfg["coint_trend"]).pvalue
    hl = half_life(fit.resid)
    sigma = float(fit.resid.std())
    stats = dict(beta=fit.beta, alpha=fit.alpha, trend=fit.trend, hl=hl, sigma=sigma, pvalue=pvalue)

    # 4. filters, in order; the first failure is the reason
    if fit.beta <= 0 and not cfg["allow_negative_beta"]:
        return spec("negative_beta", f"beta {fit.beta:.2f} <= 0", **stats)
    if pvalue >= cfg["coint_pvalue"]:
        return spec("not_cointegrated", f"p {pvalue:.3f} >= {cfg['coint_pvalue']}", **stats)
    if not cfg["halflife_min"] <= hl <= cfg["halflife_max"]:
        return spec("half_life", f"half-life {hl:.1f}d outside "
                    f"{cfg['halflife_min']}-{cfg['halflife_max']}d", **stats)
    if not _passes_cost_hurdle(sigma, cfg):
        return spec("cost", "entry_z x sigma below the cost hurdle", **stats)

    return spec("tradable", "", **stats)


def _passes_cost_hurdle(sigma: float, cfg: dict) -> bool:
    # PLACEHOLDER: always passes until costs.py exists.
    # Rule to implement: entry_z * sigma > 3 * round-trip cost across both legs.
    return True


RANKERS = {
    "half_life": lambda s: (s.half_life, s.pvalue),   # shortest half-life, p-value breaks ties
    "pvalue": lambda s: (s.pvalue, s.half_life),      # strongest evidence, half-life breaks ties
}


def _select(specs: list[PairSpec], top_n: int, rank_by: str) -> list[PairSpec]:
    """Mark the top_n tradable pairs."""
    tradable = sorted((s for s in specs if s.status == "tradable"), key=RANKERS[rank_by])
    chosen = {s.pair_id for s in tradable[:top_n]}
    return [replace(s, selected=s.pair_id in chosen) for s in specs]
