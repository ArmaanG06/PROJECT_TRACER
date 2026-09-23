"""Project Tracer data puller.

Everything except the per-source adapters lives here: settings, errors, the
Provider base class, the universe loader, the DuckDB store, and get_prices().
One file per source sits alongside: ibkr.py, wrds.py, yfinance.py.

Prices live in one DuckDB file per program (data/store/ROME.duckdb), schema in
data/schema.sql. The files are gitignored; rebuild with data/build_db.py.

    from data_pulling import get_prices, to_wide, load_universe

That works from any directory, including programs/ROME/, because pyproject.toml
maps the name `data_pulling` onto data/data_pulling/ and the package is
installed editable. No sys.path hacks.

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

import pandas as pd
import yaml

logger = logging.getLogger(__name__)
logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "0.1.0"

#: Canonical frame columns every provider returns.
COLUMNS = ("date", "open", "high", "low", "close", "adj_close", "volume")

#: Failover order. get_prices(source=...) starts here and works down the list.
PROVIDER_ORDER = ("ibkr", "wrds", "yfinance")


# ======================================================================
# Errors -- the failover logic keys off these types
# ======================================================================
class TracerDataError(Exception):
    """Base class for data-layer errors."""


class ProviderUnavailable(TracerDataError):
    """The source is unreachable or rejected our credentials."""


class SymbolNotFound(TracerDataError):
    """The source is up but does not know this symbol."""


class CoverageError(TracerDataError):
    """The source cannot cover the requested date range."""


class DataUnavailableError(TracerDataError):
    """No source could satisfy the request. ``failures`` is {source: {symbol: why}}."""

    def __init__(self, failures: dict[str, dict[str, str]]):
        self.failures = failures
        lines = ["No source could satisfy the request."]
        for source, per_symbol in failures.items():
            for symbol, reason in per_symbol.items():
                lines.append(f"  {source} / {symbol}: {reason}")
        super().__init__("\n".join(lines))


# ======================================================================
# Settings
# ======================================================================
def project_root() -> Path:
    """Repo root, found by walking up to the directory holding pyproject.toml."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return here.parents[2]


@lru_cache(maxsize=1)
def settings() -> dict[str, Any]:
    """Load config/settings.yaml once per process."""
    path = project_root() / "config" / "settings.yaml"
    if not path.exists():
        logger.warning("[data_pulling] no config at %s; using defaults", path)
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def setting(dotted: str, default: Any = None) -> Any:
    """Fetch a setting by dotted path, e.g. ``providers.ibkr.port``."""
    node: Any = settings()
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def store_path(name: str) -> Path:
    """A configured path under data/store/, resolved against the repo root."""
    raw = setting(f"paths.{name}", f"data/store/{name}")
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else project_root() / candidate


def configure_logging(level: str | int | None = None) -> None:
    """Attach a terminal handler so failover warnings are visible."""
    # Windows consoles default to cp1252, which cannot encode the arrow in the
    # failover switch line and would mangle or crash the output.
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    log = logging.getLogger(__name__)
    log.setLevel(level or setting("logging.level", "INFO"))
    if not any(isinstance(h, logging.StreamHandler) for h in log.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
        log.addHandler(handler)
    log.propagate = False


# ======================================================================
# Universes
# ======================================================================
def load_universe(name: str) -> pd.DataFrame:
    """Load data/store/universes/<NAME>_constituents.csv.

    Returns a frame of symbol / group / description, de-duplicated and sorted.
    """
    path = store_path("universes") / f"{name.upper()}_constituents.csv"
    if not path.exists():
        raise FileNotFoundError(f"No universe file for {name!r} at {path}")

    frame = pd.read_csv(path, skip_blank_lines=True, encoding="utf-8")
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    if "symbol" not in frame.columns:
        raise ValueError(f"{path} has no 'Symbol' column")

    frame = frame.dropna(subset=["symbol"]).copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame = frame[frame["symbol"] != ""]
    for optional in ("group", "description"):
        frame[optional] = frame.get(optional, "").fillna("").astype(str).str.strip()

    frame = frame.drop_duplicates(subset="symbol")
    return frame[["symbol", "group", "description"]].sort_values(
        ["group", "symbol"]
    ).reset_index(drop=True)


def load_symbols(name: str) -> list[str]:
    """Just the ticker list for a universe."""
    return load_universe(name)["symbol"].tolist()


# ======================================================================
# Provider base -- the canonical frame contract
# ======================================================================
def to_timestamp(value: str | date | datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    """Normalise a date-ish value to a tz-naive Timestamp."""
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    if stamp.tz is not None:
        stamp = stamp.tz_localize(None)
    return stamp.normalize()


class Provider(abc.ABC):
    """A single data source.

    Subclasses implement healthcheck() and _fetch_raw(); they get schema
    normalisation, trimming and coverage enforcement from fetch() for free.
    """

    name = "base"
    adjustment = "unknown"

    @abc.abstractmethod
    def healthcheck(self) -> bool:
        """True if the source is reachable. Must not raise."""

    @abc.abstractmethod
    def _fetch_raw(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Fetch one symbol. May return extra rows outside the window."""

    def fetch(self, symbol: str, start, end=None) -> pd.DataFrame:
        """Fetch one symbol's daily bars in the canonical shape."""
        start_ts = to_timestamp(start)
        end_ts = to_timestamp(end) or pd.Timestamp.today().normalize()
        if start_ts > end_ts:
            raise ValueError(f"start {start_ts.date()} is after end {end_ts.date()}")

        frame = self._fetch_raw(symbol.upper(), start_ts, end_ts)
        if frame is None or len(frame) == 0:
            raise SymbolNotFound(f"{self.name} returned no rows for {symbol}")

        frame = frame.copy()
        frame.columns = [str(c).strip().lower() for c in frame.columns]
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        if isinstance(frame["date"].dtype, pd.DatetimeTZDtype):
            frame["date"] = frame["date"].dt.tz_localize(None)
        frame["date"] = frame["date"].dt.normalize()
        frame = frame.dropna(subset=["date"])

        for column in COLUMNS[1:]:
            if column not in frame.columns:
                frame[column] = pd.NA
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame = (
            frame[list(COLUMNS)]
            .sort_values("date")
            .drop_duplicates(subset="date", keep="last")
            .reset_index(drop=True)
        )

        if frame["adj_close"].isna().all():
            logger.warning(
                "[data_pulling] %s gave no adj_close for %s; using raw close "
                "(NOT total-return adjusted)", self.name, symbol,
            )
            frame["adj_close"] = frame["close"]

        # Trim after normalising: IBKR must request a full duration (see
        # ibkr.py) and relies on this to cut back to the window.
        frame = frame[
            (frame["date"] >= start_ts) & (frame["date"] <= end_ts)
        ].reset_index(drop=True)
        if frame.empty:
            raise CoverageError(
                f"{self.name} has no data for {symbol} between "
                f"{start_ts.date()} and {end_ts.date()}"
            )

        # End-side coverage is strict: a series stopping short means the source
        # is stale or broken, which is worth failing over for. Start-side is
        # not: an ETF may not have existed yet (SIL, GDXJ, EMB all post-date
        # 2010) and no other source can invent history.
        slack = pd.Timedelta(days=int(setting("coverage_slack_days", 5)))
        if frame["date"].iloc[-1] < end_ts - slack:
            raise CoverageError(
                f"{self.name} coverage for {symbol} ends "
                f"{frame['date'].iloc[-1].date()}, short of {end_ts.date()}"
            )
        if frame["date"].iloc[0] > start_ts + slack:
            logger.warning(
                "[data_pulling] %s: %s starts %s, after requested %s (short history)",
                self.name, symbol, frame["date"].iloc[0].date(), start_ts.date(),
            )
        return frame


_PROVIDERS: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    """Return (and cache) a provider. Imported lazily so nothing opens a
    socket, or needs every vendor library installed, just to import this."""
    key = name.lower()
    if key not in _PROVIDERS:
        if key == "ibkr":
            from .ibkr import IbkrProvider as cls
        elif key == "wrds":
            from .wrds import WrdsProvider as cls
        elif key == "yfinance":
            from .yfinance import YfinanceProvider as cls
        else:
            raise KeyError(f"Unknown source {name!r}; expected one of {list(PROVIDER_ORDER)}")
        _PROVIDERS[key] = cls()
    return _PROVIDERS[key]


def reset_providers() -> None:
    """Close and drop every cached provider."""
    for provider in _PROVIDERS.values():
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    _PROVIDERS.clear()


def failover_chain(source: str) -> list[str]:
    """Sources to try, starting at ``source``, never repeating one."""
    key = source.lower()
    if key not in PROVIDER_ORDER:
        raise KeyError(f"Unknown source {source!r}; expected one of {list(PROVIDER_ORDER)}")
    return [key] + [name for name in PROVIDER_ORDER if name != key]


# ======================================================================
# DuckDB store: one database per program, data/store/<PROGRAM>.duckdb
#
# Schema lives in data/schema.sql. The .duckdb files are gitignored; rebuild
# one with `python data/build_db.py ROME --fill`.
#
# meta's primary key is symbol alone, so a symbol physically cannot hold two
# sources at once -- the no-mixing rule is enforced by the database, not by
# convention. Writes replace a symbol wholesale.
# ======================================================================
_PRICE_COLUMNS = "symbol, date, open, high, low, close, adj_close, volume, source"


def db_path(db: str) -> Path:
    """Path to a program's database file, e.g. db_path("ROME")."""
    return store_path("db") / f"{db.upper()}.duckdb"


_CONNECTIONS: dict[str, Any] = {}


def connect(db: str):
    """Open the program database, creating it from data/schema.sql if needed.

    Connections are reused: opening a DuckDB file costs ~13ms while the queries
    themselves take under 1ms, so open-per-call would dominate the runtime.
    Call close_db() to release the file lock.
    """
    import duckdb

    path = db_path(db)
    key = str(path)
    existing = _CONNECTIONS.get(key)
    if existing is not None:
        try:
            existing.execute("SELECT 1")
            return existing
        except Exception:  # connection went stale; reopen below
            _CONNECTIONS.pop(key, None)

    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(key)
    con.execute((project_root() / "data" / "schema.sql").read_text(encoding="utf-8"))
    _CONNECTIONS[key] = con
    return con


def close_db(db: str | None = None) -> None:
    """Close cached connection(s), releasing the DuckDB file lock."""
    keys = [str(db_path(db))] if db is not None else list(_CONNECTIONS)
    for key in keys:
        con = _CONNECTIONS.pop(key, None)
        if con is not None:
            try:
                con.close()
            except Exception:
                pass


def cache_save(source: str, symbol: str, frame: pd.DataFrame, db: str) -> None:
    """Write a series, replacing any existing rows for that symbol."""
    symbol = symbol.upper()
    payload = frame.copy()
    payload["symbol"] = symbol
    payload["source"] = source
    payload["date"] = pd.to_datetime(payload["date"]).dt.date

    con = connect(db)
    con.register("incoming", payload)
    # Delete-then-insert, in one transaction: a symbol is replaced wholesale,
    # never appended to, so it can never end up half from one source and half
    # from another.
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM prices WHERE symbol = ?", [symbol])
        con.execute(f"INSERT INTO prices SELECT {_PRICE_COLUMNS} FROM incoming")
        con.execute("DELETE FROM meta WHERE symbol = ?", [symbol])
        con.execute(
            "INSERT INTO meta VALUES (?, ?, ?, ?, ?, ?, current_timestamp)",
            [
                symbol,
                source,
                payload["date"].min(),
                payload["date"].max(),
                len(payload),
                getattr(get_provider(source), "adjustment", "unknown"),
            ],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.unregister("incoming")


def cache_load(source: str, symbol: str, db: str) -> pd.DataFrame | None:
    """Read a cached series for this symbol AND source, or None."""
    path = db_path(db)
    if not path.exists():
        return None
    try:
        frame = connect(db).execute(
            "SELECT date, open, high, low, close, adj_close, volume FROM prices "
            "WHERE symbol = ? AND source = ? ORDER BY date",
            [symbol.upper(), source],
        ).df()
    except Exception as exc:
        logger.warning("[data_pulling] store read failed for %s: %s", symbol, exc)
        return None

    if frame.empty:
        return None
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def cache_status(db: str) -> pd.DataFrame:
    """Summarise the store: symbol, source, range, rows, last pull, staleness."""
    columns = ["symbol", "source", "start", "end", "rows", "adjustment",
               "pulled", "stale_days"]
    path = db_path(db)
    if not path.exists():
        return pd.DataFrame(columns=columns)

    frame = connect(db).execute(
        "SELECT symbol, source, start_date AS start, end_date AS end, rows, "
        "adjustment, pulled_at AS pulled, "
        "date_diff('day', end_date, current_date) AS stale_days "
        "FROM meta ORDER BY symbol"
    ).df()
    return frame if not frame.empty else pd.DataFrame(columns=columns)


# ======================================================================
# The puller
# ======================================================================
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
                return cached[
                    (cached["date"] >= start) & (cached["date"] <= end)
                ].reset_index(drop=True)

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
