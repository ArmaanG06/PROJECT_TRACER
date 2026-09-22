"""Provider interface and the canonical frame shape.

Every provider returns the same columns so sources are interchangeable:

    date | open | high | low | close | adj_close | volume

``date`` is tz-naive, sorted, de-duplicated. ``adj_close`` is always
total-return adjusted (splits and dividends).
"""

from __future__ import annotations

import abc
import logging
from datetime import date, datetime

import pandas as pd

from ..config import get_settings
from ..errors import CoverageError, SymbolNotFound

logger = logging.getLogger(__name__)

COLUMNS = ("date", "open", "high", "low", "close", "adj_close", "volume")


def to_timestamp(value: str | date | datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    """Normalise a date-ish value to a tz-naive Timestamp."""
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    if stamp.tz is not None:
        stamp = stamp.tz_localize(None)
    return stamp.normalize()


class Provider(abc.ABC):
    """A single data source."""

    name = "base"
    adjustment = "unknown"

    @abc.abstractmethod
    def healthcheck(self) -> bool:
        """True if the source is reachable. Must not raise."""

    @abc.abstractmethod
    def _fetch_raw(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Fetch one symbol. May return extra rows outside the window."""

    def fetch(self, symbol: str, start, end=None) -> pd.DataFrame:
        """Fetch one symbol's daily bars in the canonical shape.

        Raises:
            ProviderUnavailable, SymbolNotFound, CoverageError.
        """
        start_ts = to_timestamp(start)
        end_ts = to_timestamp(end) or pd.Timestamp.today().normalize()
        if start_ts > end_ts:
            raise ValueError(f"start {start_ts.date()} is after end {end_ts.date()}")

        raw = self._fetch_raw(symbol.upper(), start_ts, end_ts)
        return self._finalize(raw, symbol.upper(), start_ts, end_ts)

    def _finalize(self, frame, symbol, start, end) -> pd.DataFrame:
        """Enforce the schema, trim to the window, check coverage."""
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
                "(NOT total-return adjusted)",
                self.name,
                symbol,
            )
            frame["adj_close"] = frame["close"]

        # Trim after normalising: IBKR has to request a full duration (see
        # providers/ibkr.py) and relies on this to cut back to the window.
        frame = frame[(frame["date"] >= start) & (frame["date"] <= end)].reset_index(drop=True)
        if frame.empty:
            raise CoverageError(
                f"{self.name} has no data for {symbol} between {start.date()} and {end.date()}"
            )

        # End-side coverage is strict: a series that stops short means the
        # source is stale or broken, and that is worth failing over for.
        # Start-side is not: an ETF may simply not have existed yet (SIL, GDXJ
        # and EMB all post-date 2010), and no other source can invent history.
        slack = pd.Timedelta(days=int(get_settings().get("coverage_slack_days", 5)))
        last = frame["date"].iloc[-1]
        if last < end - slack:
            raise CoverageError(
                f"{self.name} coverage for {symbol} ends {last.date()}, "
                f"short of requested end {end.date()}"
            )

        first = frame["date"].iloc[0]
        if first > start + slack:
            logger.warning(
                "[data_pulling] %s: %s starts %s, after requested %s (short history)",
                self.name,
                symbol,
                first.date(),
                start.date(),
            )

        return frame
