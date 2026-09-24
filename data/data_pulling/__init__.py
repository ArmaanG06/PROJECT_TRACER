"""Project Tracer data puller.

Everything except the per-source adapters lives here: settings, errors, the
Provider base class, the universe loader, the DuckDB store, and get_prices().
One file per source sits alongside: ibkr.py, wrds.py, yfinance.py.

Prices live in one DuckDB file per program (data/store/ROME.duckdb), schema in
data/schema.sql. The files are gitignored; rebuild with data/build_db.py.

    from data_pulling import get_prices, to_wide, load_universe

That works from any directory, including programs/ROME/, because pyproject.toml
maps the name `data_pulling` onto data/data_pulling/ and the package is
installed editable.

THE NO-MIXING RULE: a symbol's series always comes from exactly one source.
Ranges are never spliced across vendors -- if IB covers 2010-2020 and Yahoo
covers 2020-2026, the answer is "IB failed, use Yahoo for all of it", not both.
Adjustment methods and dividend timing differ between vendors, so a stitched
series shows a return on the join date that never happened.
"""

from __future__ import annotations

import abc
import logging
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal
from utils.utils import load_config
from data_errors import TracerDataError, ProviderUnavailable, SymbolNotFound, CoverageError, DataUnavailableError
from data_helper import cache_load, cache_save, get_provider, failover_chain, to_timestamp


import pandas as pd
import yaml

logger = logging.getLogger(__name__)
logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "0.1.0"

#: Canonical frame columns every provider returns.
configs = load_config()
COLUMNS = configs['data']['columns'] 

#: Failover order. get_prices(source=...) starts here and works down the list.
PROVIDER_ORDER = configs['data']['provider_order'] 

# ======================================================================
# The puller
# ======================================================================

## EVERYTHING OTHER THAN BELOW HERE COULD BE IN A HELPER FILE FOR EASE OF VISION AND MIND
_FAILOVER_ERRORS = (ProviderUnavailable, SymbolNotFound, CoverageError)


def _reason(exc: BaseException, limit: int = 110) -> str:
    text = " ".join(str(exc).split()) or type(exc).__name__
    return text[: limit - 1] + "…" if len(text) > limit else text


def _fetch_one(source, symbol, start, end, use_cache, refresh, db) -> pd.DataFrame:
    """One symbol from one source, served from the store when it covers the range."""
    # No db named means no program database to use, so go straight to the
    # provider. There is no sensible global default: the database belongs to
    # the program, and only the caller knows which program it is.
    store = use_cache and db is not None
    if store and not refresh:
        cached = cache_load(source, symbol, db)
        if cached is not None and not cached.empty:
            if cached["date"].iloc[0] <= start and cached["date"].iloc[-1] >= end:
                return cached[(cached["date"] >= start) & (cached["date"] <= end)].reset_index(drop=True)

    frame = get_provider(source).fetch(symbol, start, end)
    if store:
        cache_save(source, symbol, frame, db)
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
    db: str | None = None,
) -> pd.DataFrame:
    """Fetch daily total-return-adjusted bars.

    Args:
        symbols: One ticker or an iterable of tickers.
        start: First date, inclusive.
        end: Last date, inclusive. None means latest available.
        source: Preferred source; the failover chain starts here and continues
            ibkr -> wrds -> yfinance, skipping anything already tried.
        fallback: Try the remaining sources on failure. False re-raises the
            first provider error untouched.
        mode: "strict" (default) requires every symbol to come from one source
            -- any failure retries the WHOLE basket on the next source.
            "per_symbol" lets each symbol fail over independently.
        use_cache: Read from and write to the program database.
        refresh: Ignore the store and re-pull.
        db: Which program's database to read and write, e.g. "ROME"
            (data/store/ROME.duckdb). Omit it and nothing is stored -- the
            data comes straight from the provider.

    Returns:
        Tidy long frame: date, open, high, low, close, adj_close, volume,
        symbol, source. Dates tz-naive, sorted, unique per symbol.

    Raises:
        DataUnavailableError: No source could satisfy the request.

    Example:
        >>> prices = get_prices(["GLD", "GDX"], "2010-01-01", source="ibkr")
        >>> to_wide(prices).tail()
    """
    raw = [symbols] if isinstance(symbols, str) else list(symbols)
    tickers = list(dict.fromkeys(str(s).strip().upper() for s in raw if str(s).strip()))
    if not tickers:
        raise ValueError("no symbols requested")

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
            error = failed = None
            for symbol in tickers:
                try:
                    attempt[symbol] = (
                        _fetch_one(src, symbol, start_ts, end_ts, use_cache, refresh, db), src
                    )
                except _FAILOVER_ERRORS as exc:
                    if not fallback:
                        raise
                    error, failed = exc, symbol
                    break  # no point burning paced requests on a doomed source
            if error is None:
                resolved = attempt
                break
            failures.setdefault(src, {})[failed] = _reason(error)
            if index + 1 < len(chain):
                logger.warning(
                    "[data_pulling] %s failed for %s (reason: %s) → switched to %s",
                    src, failed, _reason(error), chain[index + 1],
                )
    else:
        for symbol in tickers:
            for index, src in enumerate(chain):
                try:
                    resolved[symbol] = (
                        _fetch_one(src, symbol, start_ts, end_ts, use_cache, refresh, db), src
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

    if len({src for _, src in resolved.values()}) > 1:
        mix = "; ".join(f"{src}: {sym}" for sym, (_, src) in sorted(resolved.items()))
        logger.warning("[data_pulling] MIXED basket — %s", mix)

    combined = pd.concat(
        [frame.assign(symbol=sym, source=src) for sym, (frame, src) in resolved.items()],
        ignore_index=True,
    )
    return combined[[*COLUMNS, "symbol", "source"]].sort_values(
        ["date", "symbol"]
    ).reset_index(drop=True)


def to_wide(df: pd.DataFrame, field: str = "adj_close") -> pd.DataFrame:
    """Pivot a tidy long frame to date x symbol."""
    if field not in df.columns:
        raise KeyError(f"{field!r} is not a column; have {sorted(df.columns)}")
    wide = df.pivot_table(index="date", columns="symbol", values=field, aggfunc="last")
    wide.columns.name = None
    return wide.sort_index().reindex(sorted(wide.columns), axis=1)
