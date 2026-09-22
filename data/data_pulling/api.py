"""The unified data API: get_prices() and to_wide().

**The no-mixing rule.** A symbol's series always comes from exactly one
provider. Date ranges are never spliced across sources: if IB covers 2010-2020
and Yahoo covers 2020-2026, the answer is not "both", it is "IB failed, use
Yahoo for the whole thing" -- or an error. Two vendors' adjustment methods and
dividend timing do not line up, so a stitched series produces a return on the
join date that never happened.
"""

from __future__ import annotations

import logging
from typing import Iterable, Literal

import pandas as pd

from . import store
from .errors import CoverageError, DataUnavailableError, ProviderUnavailable, SymbolNotFound
from .providers import failover_chain, get_provider
from .providers.base import COLUMNS, to_timestamp

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = (*COLUMNS, "symbol", "source")

# Failures that trigger failover. Anything else is a bug and propagates.
_FAILOVER_ERRORS = (ProviderUnavailable, SymbolNotFound, CoverageError)


def _reason(exc: BaseException, limit: int = 110) -> str:
    text = " ".join(str(exc).split()) or type(exc).__name__
    return text[: limit - 1] + "…" if len(text) > limit else text


def _symbols(symbols: str | Iterable[str]) -> list[str]:
    raw = [symbols] if isinstance(symbols, str) else list(symbols)
    out = list(dict.fromkeys(str(s).strip().upper() for s in raw if str(s).strip()))
    if not out:
        raise ValueError("no symbols requested")
    return out


def _fetch_one(source, symbol, start, end, use_cache, refresh) -> pd.DataFrame:
    """Fetch one symbol from one source, via the cache when it covers the range."""
    if use_cache and not refresh:
        cached = store.load(source, symbol)
        if cached is not None and not cached.empty:
            if cached["date"].iloc[0] <= start and cached["date"].iloc[-1] >= end:
                return cached[
                    (cached["date"] >= start) & (cached["date"] <= end)
                ].reset_index(drop=True)

    frame = get_provider(source).fetch(symbol, start, end)
    if use_cache:
        store.save(source, symbol, frame)
    return frame


def get_prices(
    symbols: str | Iterable[str],
    start,
    end=None,
    source: Literal["ibkr", "wrds", "yfinance"] = "ibkr",
    fallback: bool = True,
    mode: Literal["strict", "per_symbol"] = "strict",
    use_cache: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch daily total-return-adjusted bars.

    Args:
        symbols: One ticker or an iterable of tickers.
        start: First date, inclusive.
        end: Last date, inclusive. None means latest available.
        source: Preferred source; the failover chain starts here.
        fallback: Try the remaining sources on failure. False re-raises the
            first provider error untouched.
        mode: "strict" (default) requires every symbol in the call to come from
            the same source -- any failure retries the whole basket on the next
            source. "per_symbol" lets each symbol fail over on its own.
        use_cache: Read from and write to the parquet cache.
        refresh: Ignore the cache and re-pull.

    Returns:
        Tidy long DataFrame: date, open, high, low, close, adj_close, volume,
        symbol, source. Dates tz-naive, sorted, unique per symbol.

    Raises:
        DataUnavailableError: No source could satisfy the request.

    Example:
        >>> from data_pulling import get_prices, to_wide
        >>> prices = get_prices(["GLD", "GDX"], "2010-01-01", source="ibkr")
        >>> to_wide(prices).tail()
    """
    tickers = _symbols(symbols)
    start_ts = to_timestamp(start)
    end_ts = to_timestamp(end) or pd.Timestamp.today().normalize()
    if start_ts > end_ts:
        raise ValueError(f"start {start_ts.date()} is after end {end_ts.date()}")
    if mode not in ("strict", "per_symbol"):
        raise ValueError(f"mode must be 'strict' or 'per_symbol', got {mode!r}")

    chain = failover_chain(source) if fallback else [source.lower()]
    failures: dict[str, dict[str, str]] = {}
    resolved: dict[str, tuple[pd.DataFrame, str]] = {}

    if mode == "strict":
        # The basket is atomic: one symbol failing moves ALL of them to the
        # next source, and this source's partial results are discarded.
        for index, src in enumerate(chain):
            attempt: dict[str, tuple[pd.DataFrame, str]] = {}
            error = failed_symbol = None
            for symbol in tickers:
                try:
                    attempt[symbol] = (
                        _fetch_one(src, symbol, start_ts, end_ts, use_cache, refresh),
                        src,
                    )
                except _FAILOVER_ERRORS as exc:
                    if not fallback:
                        raise
                    error, failed_symbol = exc, symbol
                    break  # no point burning paced requests on a doomed source
            if error is None:
                resolved = attempt
                break
            failures.setdefault(src, {})[failed_symbol] = _reason(error)
            if index + 1 < len(chain):
                logger.warning(
                    "[data_pulling] %s failed for %s (reason: %s) → switched to %s",
                    src, failed_symbol, _reason(error), chain[index + 1],
                )
    else:
        for symbol in tickers:
            for index, src in enumerate(chain):
                try:
                    resolved[symbol] = (
                        _fetch_one(src, symbol, start_ts, end_ts, use_cache, refresh),
                        src,
                    )
                    break
                except _FAILOVER_ERRORS as exc:
                    if not fallback:
                        raise
                    failures.setdefault(src, {})[symbol] = _reason(exc)
                    if index + 1 < len(chain):
                        logger.warning(
                            "[data_pulling] %s failed for %s (reason: %s) → switched to %s",
                            src, symbol, _reason(exc), chain[index + 1],
                        )

    if len(resolved) != len(tickers):
        raise DataUnavailableError(failures)

    used = {src for _, src in resolved.values()}
    if len(used) > 1:
        mix = "; ".join(f"{s}: {sym}" for sym, (_, s) in sorted(resolved.items()))
        logger.warning("[data_pulling] MIXED basket — %s", mix)

    parts = []
    for symbol, (frame, src) in resolved.items():
        parts.append(frame.assign(symbol=symbol, source=src))
    combined = pd.concat(parts, ignore_index=True)[list(OUTPUT_COLUMNS)]
    return combined.sort_values(["date", "symbol"]).reset_index(drop=True)


def to_wide(df: pd.DataFrame, field: str = "adj_close") -> pd.DataFrame:
    """Pivot a tidy long frame to date x symbol.

    Args:
        df: Output of get_prices().
        field: Column to spread, e.g. adj_close, close, volume.
    """
    if field not in df.columns:
        raise KeyError(f"{field!r} is not a column; have {sorted(df.columns)}")
    wide = df.pivot_table(index="date", columns="symbol", values=field, aggfunc="last")
    wide.columns.name = None
    return wide.sort_index().reindex(sorted(wide.columns), axis=1)
