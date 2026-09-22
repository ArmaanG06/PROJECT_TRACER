"""yfinance provider -- last resort, logs a WARNING every time it is used.

What Yahoo's adjustment covers: ``Adj Close`` is adjusted for splits **and**
cash dividends, so it is a total-return series like IB's ADJUSTED_LAST and a
CRSP return index. ``Close`` is adjusted for splits only. The caveat is data
quality, not definition -- Yahoo sometimes misses or mistimes distributions.

``auto_adjust`` is passed explicitly on every call, because yfinance flipped
its default to True: under that default the ``Adj Close`` column disappears and
``Close`` is silently overwritten with the adjusted series.
"""

from __future__ import annotations

import logging

import pandas as pd

from . import Provider, ProviderUnavailable, SymbolNotFound, setting

logger = logging.getLogger(__name__)


class YfinanceProvider(Provider):
    """Daily bars from Yahoo Finance."""

    name = "yfinance"
    adjustment = "yahoo_adj_close"

    def __init__(self):
        config = setting("providers.yfinance", {}) or {}
        self.auto_adjust = bool(config.get("auto_adjust", False))

    def healthcheck(self) -> bool:
        try:
            import yfinance as yf

            probe = yf.Ticker("SPY").history(period="5d", auto_adjust=False)
            return probe is not None and not probe.empty
        except Exception:
            return False

    def _fetch_raw(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        logger.warning("[data_pulling] using yfinance for %s — last-resort source", symbol)
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderUnavailable(f"yfinance is not installed: {exc}") from exc

        try:
            frame = yf.Ticker(symbol).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),  # end is exclusive
                interval="1d",
                auto_adjust=self.auto_adjust,  # explicit: see module docstring
                raise_errors=True,
            )
        except Exception as exc:
            raise ProviderUnavailable(f"Yahoo request failed for {symbol}: {exc}") from exc

        if frame is None or frame.empty:
            raise SymbolNotFound(f"Yahoo returned no rows for {symbol}")

        frame = frame.reset_index()
        frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]
        frame = frame.rename(columns={"datetime": "date", "index": "date"})

        if "adj_close" not in frame.columns:
            # auto_adjust=True drops Adj Close and puts the adjusted series in
            # Close. Label it honestly rather than emitting a raw close as adjusted.
            frame["adj_close"] = frame["close"]

        return frame
