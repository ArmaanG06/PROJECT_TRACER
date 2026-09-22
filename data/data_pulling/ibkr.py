"""IBKR provider, via ib_async (the maintained successor to ib_insync).

Two requests per symbol: ADJUSTED_LAST for adj_close (splits + dividends) and
TRADES for raw OHLCV.

ADJUSTED_LAST only works with a **blank** endDateTime -- an explicit end date
returns error 162. So both requests ask for a duration long enough to reach
back past `start`, and Provider._finalize trims the result locally.
"""

from __future__ import annotations

import logging
import math
import time

import pandas as pd

from . import Provider, ProviderUnavailable, SymbolNotFound, setting

logger = logging.getLogger(__name__)


class IbkrProvider(Provider):
    """Daily bars from a running TWS or IB Gateway session."""

    name = "ibkr"
    adjustment = "ib_adjusted_last"

    def __init__(self):
        config = setting("providers.ibkr", {}) or {}
        self.host = str(config.get("host", "127.0.0.1"))
        self.port = int(config.get("port", 7497))
        self.client_id = int(config.get("client_id", 11))
        self.timeout = float(config.get("timeout", 30))
        self.pace = float(config.get("pace_seconds", 2.5))
        self._ib = None
        self._last_request = 0.0

    def _connect(self):
        if self._ib is not None and self._ib.isConnected():
            return self._ib
        try:
            from ib_async import IB
        except ImportError as exc:
            raise ProviderUnavailable(f"ib_async is not installed: {exc}") from exc

        ib = IB()
        try:
            # readonly=True so this layer can never transmit an order.
            ib.connect(
                self.host, self.port, clientId=self.client_id,
                timeout=self.timeout, readonly=True,
            )
        except Exception as exc:
            raise ProviderUnavailable(
                f"cannot reach TWS/Gateway at {self.host}:{self.port}: {exc}"
            ) from exc

        self._ib = ib
        logger.info("[data_pulling] ibkr connected to %s:%s", self.host, self.port)
        return ib

    def close(self) -> None:
        """Disconnect if connected."""
        if self._ib is not None:
            try:
                if self._ib.isConnected():
                    self._ib.disconnect()
            except Exception:
                pass
            self._ib = None

    def healthcheck(self) -> bool:
        try:
            return self._connect().isConnected()
        except Exception:
            return False

    def _bars(self, ib, contract, what: str, years: int) -> pd.DataFrame:
        """One paced reqHistoricalData call."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.pace:
            time.sleep(self.pace - elapsed)
        self._last_request = time.monotonic()

        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",  # must be blank for ADJUSTED_LAST (else error 162)
            durationStr=f"{years} Y",
            barSizeSetting="1 day",
            whatToShow=what,
            useRTH=True,
            formatDate=1,
        )
        if not bars:
            return pd.DataFrame()

        from ib_async import util

        frame = util.df(bars)
        frame["date"] = pd.to_datetime(frame["date"])
        return frame

    def _fetch_raw(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        from ib_async import Stock

        ib = self._connect()
        qualified = ib.qualifyContracts(Stock(symbol, "SMART", "USD"))
        if not qualified:
            raise SymbolNotFound(f"IB does not recognise {symbol}")
        contract = qualified[0]

        days = (pd.Timestamp.today().normalize() - start).days
        years = max(1, min(30, math.ceil(days / 365) + 1))

        adjusted = self._bars(ib, contract, "ADJUSTED_LAST", years)
        trades = self._bars(ib, contract, "TRADES", years)

        if adjusted.empty and trades.empty:
            raise SymbolNotFound(f"IB returned no bars for {symbol}")
        if trades.empty:
            return adjusted.assign(adj_close=adjusted["close"])
        if adjusted.empty:
            return trades

        adj = adjusted[["date", "close"]].rename(columns={"close": "adj_close"})
        return trades.merge(adj, on="date", how="outer")
