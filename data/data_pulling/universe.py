"""Universe files: the list of symbols an algo trades.

One CSV per universe under ``data/store/universes/<NAME>_constituents.csv`` with
columns ``Symbol,Group,Description``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import get_settings

logger = logging.getLogger(__name__)


def universe_path(name: str) -> Path:
    """Return the CSV path for a universe, e.g. ``ROME``."""
    return get_settings().path("universes") / f"{name.upper()}_constituents.csv"


def load_universe(name: str) -> pd.DataFrame:
    """Load a universe definition.

    Args:
        name: Universe name, case-insensitive (e.g. ``"ROME"``).

    Returns:
        DataFrame with columns ``symbol``, ``group``, ``description``, one row
        per instrument, de-duplicated on ``symbol`` and sorted by group then
        symbol.

    Raises:
        FileNotFoundError: If the universe CSV does not exist.
        ValueError: If the CSV has no ``Symbol`` column or is empty.
    """
    path = universe_path(name)
    if not path.exists():
        raise FileNotFoundError(f"No universe file for {name!r} at {path}")

    # skip_blank_lines guards against the hand-maintained grouping style the
    # original file used, where blank lines separated sectors.
    frame = pd.read_csv(path, skip_blank_lines=True, encoding="utf-8")
    frame.columns = [str(c).strip().lower() for c in frame.columns]

    if "symbol" not in frame.columns:
        raise ValueError(f"{path} has no 'Symbol' column (found {list(frame.columns)})")

    frame = frame.dropna(subset=["symbol"]).copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame = frame[frame["symbol"] != ""]

    for optional in ("group", "description"):
        if optional not in frame.columns:
            frame[optional] = ""
        frame[optional] = frame[optional].fillna("").astype(str).str.strip()

    duplicates = frame["symbol"].duplicated()
    if duplicates.any():
        dropped = sorted(frame.loc[duplicates, "symbol"].unique())
        logger.warning("Universe %s has duplicate symbols, keeping first: %s", name, dropped)
        frame = frame[~duplicates]

    if frame.empty:
        raise ValueError(f"Universe {name!r} at {path} contains no symbols")

    return (
        frame[["symbol", "group", "description"]]
        .sort_values(["group", "symbol"])
        .reset_index(drop=True)
    )


def load_symbols(name: str) -> list[str]:
    """Return just the ticker list for a universe."""
    return load_universe(name)["symbol"].tolist()


def list_universes() -> list[str]:
    """Return the names of every universe file on disk."""
    directory = get_settings().path("universes")
    if not directory.exists():
        return []
    return sorted(
        p.name.replace("_constituents.csv", "")
        for p in directory.glob("*_constituents.csv")
    )
