"""Dead-simple parquet cache: one file per source per symbol.

    data/store/cache/<source>/<SYMBOL>.parquet

Keyed by (source, symbol), never by symbol alone -- that is what keeps two
sources' series for the same ticker from ever overwriting each other.
"""

from __future__ import annotations

import logging

import pandas as pd

from .config import get_settings

logger = logging.getLogger(__name__)


def cache_path(source: str, symbol: str):
    """Where a given series lives on disk."""
    return get_settings().path("cache") / source / f"{symbol.upper()}.parquet"


def save(source: str, symbol: str, frame: pd.DataFrame) -> None:
    """Write a series to the cache, replacing whatever was there."""
    path = cache_path(source, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def load(source: str, symbol: str) -> pd.DataFrame | None:
    """Read a cached series, or None if it is not cached."""
    path = cache_path(source, symbol)
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        logger.warning("[data_pulling] unreadable cache file %s: %s", path, exc)
        return None
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").reset_index(drop=True)


def status() -> pd.DataFrame:
    """Summarise everything in the cache, for `tracer data status`."""
    root = get_settings().path("cache")
    rows = []
    if root.exists():
        for path in sorted(root.glob("*/*.parquet")):
            try:
                frame = pd.read_parquet(path, columns=["date"])
            except Exception:
                continue
            dates = pd.to_datetime(frame["date"])
            rows.append(
                {
                    "symbol": path.stem,
                    "source": path.parent.name,
                    "start": dates.min().date(),
                    "end": dates.max().date(),
                    "rows": len(frame),
                    "pulled": pd.Timestamp(path.stat().st_mtime, unit="s").floor("s"),
                    "stale_days": (pd.Timestamp.today().normalize() - dates.max()).days,
                }
            )
    return pd.DataFrame(
        rows, columns=["symbol", "source", "start", "end", "rows", "pulled", "stale_days"]
    )
