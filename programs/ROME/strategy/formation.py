"""Monthly formation: which pairs are tradable as of refit date t.

Pure function. It sees prices <= t only, returns a PairSpec for EVERY pair (not just the
winners) so the kill/continue check can see why each pair failed. Exit-only marking of open
trades is the runner's job (state_mgmt.mark_exit_only), not formation's.
"""
from dataclasses import replace

import numpy as np
import pandas as pd

from ROME.models import PairSpec
from ROME.strategy.costs import round_trip_cost
from ROME.strategy.stats import cointegration, half_life, hedge_ratio


def form_pairs(prices: pd.DataFrame, t, pairs: pd.DataFrame, rome: dict) -> list[PairSpec]:
    """Test every pair on the window ending at t.

    prices: wide adj_close frame (dates x tickers), total-return adjusted. Can hold ALL history:
            each pair is only tested on the last X months before t (see _window).
    t:      refit date. Anything after t is dropped here as a second look-ahead guard.
    pairs:  the pairs file (symbol_a, symbol_b, rationale).
    rome:   the whole strategies.ROME section of configs.yaml (formation settings, plus
            signal.entry_z and costs for the cost hurdle).
    """
    cfg = rome["formation"]
    t = pd.Timestamp(t)
    prices = prices.loc[:t]

    specs = []
    for row in pairs.itertuples():
        spec = _test_pair(prices, t, row.symbol_a, row.symbol_b, rome)
        specs.append(spec)

    return _select(specs, cfg["top_n"], cfg["rank_by"])


def _window(prices: pd.DataFrame, t: pd.Timestamp, months: int) -> pd.DataFrame:
    """The last `months` months of prices up to and including t. THIS is where the lookback is applied.

    Example: t = 2020-01-31, months = 12 -> rows after 2019-01-31, up to 2020-01-31.
    `months` comes from configs.yaml: formation.lookback_months or formation.test_window_months.
    """
    start = t - pd.DateOffset(months=months)
    after_start = prices.index > start
    up_to_t = prices.index <= t
    return prices.loc[after_start & up_to_t]


def _test_pair(prices, t, a, b, rome) -> PairSpec:
    cfg = rome["formation"]

    def spec(status, reason, beta=np.nan, alpha=np.nan, trend=np.nan, hl=np.nan, sigma=np.nan, pvalue=np.nan):
        return PairSpec(f"{a}-{b}", a, b, beta, alpha, trend, hl, sigma, pvalue, status, reason, False, t)

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
    pvalue = cointegration(test_win[a], test_win[b], trend=cfg["coint_trend"], autolag=cfg["coint_autolag"]).pvalue
    hl = half_life(fit.resid)
    sigma = float(fit.resid.std())
    stats = dict(beta=fit.beta, alpha=fit.alpha, trend=fit.trend, hl=hl, sigma=sigma, pvalue=pvalue)

    # 4. filters, in order; the first failure is the reason
    if fit.beta <= 0 and not cfg["allow_negative_beta"]:
        return spec("negative_beta", f"beta {fit.beta:.2f} <= 0", **stats)
    if pvalue >= cfg["coint_pvalue"]:
        return spec("not_cointegrated", f"p {pvalue:.3f} >= {cfg['coint_pvalue']}", **stats)
    if not cfg["halflife_min"] <= hl <= cfg["halflife_max"]:
        return spec("half_life", f"half-life {hl:.1f}d outside " f"{cfg['halflife_min']}-{cfg['halflife_max']}d", **stats)
    # the spread the z-score will actually trade: log_a - alpha - beta * log_b (no trend removed)
    fit_spread = fit_win[a] - fit.alpha - fit.beta * fit_win[b]
    if not _passes_cost_hurdle(a, b, fit_spread, hl, prices, rome):
        return spec("cost", "entry_z x typical 20-day sigma below the cost hurdle", **stats)

    return spec("tradable", "", **stats)


def _passes_cost_hurdle(a: str, b: str, fit_spread: pd.Series, hl: float, prices: pd.DataFrame, rome: dict) -> bool:
    # costs switched off (config costs.enabled: false): nothing is rejected for costs
    if not rome["costs"]["enabled"]:
        return True

    entry_z = rome["signal"]["entry_z"]
    hurdle_mult = rome["formation"]["cost_hurdle_mult"]
    notional = rome["sizing"]["leg_notional"]
    N = rome["signal"]["zscore_lookback"]

    # use the SAME sigma the z-score uses: the N-day wiggle, not the 12-month one.
    # typical = the median of every N-day wiggle across the formation year (steadier than just the last N days)
    rolling_sigma = fit_spread.rolling(N).std()
    typical_sigma = rolling_sigma.median()

    # latest price of each leg on or before t
    price_a = prices[a].dropna().iloc[-1]
    price_b = prices[b].dropna().iloc[-1]

    # expected holding time ~ the half-life (how long the short leg is borrowed)
    holding_days = hl

    cost = round_trip_cost(price_a, price_b, notional, holding_days, rome["costs"])
    expected_move = entry_z * typical_sigma

    return expected_move > hurdle_mult * cost


RANKERS = {
    "half_life": lambda s: (s.half_life, s.pvalue),   # shortest half-life, p-value breaks ties
    "pvalue": lambda s: (s.pvalue, s.half_life),      # strongest evidence, half-life breaks ties
}


def _select(specs: list[PairSpec], top_n: int, rank_by: str) -> list[PairSpec]:
    """Mark the top_n tradable pairs."""
    tradable = sorted((s for s in specs if s.status == "tradable"), key=RANKERS[rank_by])
    chosen = {s.pair_id for s in tradable[:top_n]}
    return [replace(s, selected=s.pair_id in chosen) for s in specs]
