"""WRDS / CRSP provider. Replaces the old ROMAN_constituents_data.py script.

Three things changed in the move:

* ``crsp.stocknames`` is legacy. CRSP's Dec-2024 release was the last in the
  SIZ/FIZ formats; the current CIZ tables are ``crsp.stksecurityinfohist`` and
  ``crsp.dsf_v2`` (a.k.a. ``crsp.stkdlysecuritydata``).
* ``where ticker in {tickers}`` interpolated a Python list, producing
  ``IN ['GLD', ...]`` -- invalid SQL. Everything here uses bound parameters.
* ticker -> PERMNO is resolved **as of the query window**, since tickers get
  reused across issuers.

adj_close is a total-return index compounded from dlyret and anchored to the
last actual close, so the final adj_close equals the final raw close.

Credentials come from libpq's pgpass file only:
    Windows : %APPDATA%\\postgresql\\pgpass.conf
    Linux   : ~/.pgpass  (chmod 600)
    Format  : wrds-pgdata.wharton.upenn.edu:9737:wrds:<user>:<password>
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import get_settings
from ..errors import CoverageError, ProviderUnavailable, SymbolNotFound
from .base import Provider

logger = logging.getLogger(__name__)

WRDS_HOST = "wrds-pgdata.wharton.upenn.edu"
WRDS_PORT = "9737"


def pgpass_path() -> Path | None:
    """Where libpq looks for stored credentials on this platform."""
    override = os.environ.get("PGPASSFILE")
    if override:
        return Path(override)
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "postgresql" / "pgpass.conf" if appdata else None
    return Path.home() / ".pgpass"


def username_from_pgpass() -> str | None:
    """Read the WRDS username out of pgpass.

    Without this the wrds package falls back to the OS user and then prompts on
    stdin, which hangs an unattended pull instead of failing it. The password
    field is never read -- libpq handles that itself.
    """
    path = pgpass_path()
    if not path or not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":", 4)  # the password may contain colons
        if len(fields) < 5:
            continue
        host, port, _db, user = fields[:4]
        if host in ("*", WRDS_HOST) and port in ("*", WRDS_PORT) and user not in ("", "*"):
            return user
    return None


class WrdsProvider(Provider):
    """Daily total-return series from the CRSP US Stock database."""

    name = "wrds"
    adjustment = "crsp_total_return_index"

    def __init__(self):
        config = get_settings().provider("wrds")
        self.username = (
            config.get("username")
            or os.environ.get("TRACER_WRDS_USERNAME")
            or username_from_pgpass()
        )
        self.daily_table = config.get("daily_table", "crsp.dsf_v2")
        self.info_table = config.get("info_table", "crsp.stksecurityinfohist")
        self._db = None

    def _connect(self):
        if self._db is not None:
            return self._db
        try:
            import wrds as wrds_lib
        except ImportError as exc:
            raise ProviderUnavailable(f"wrds package is not installed: {exc}") from exc

        # Fail fast rather than let the wrds package prompt on stdin.
        if not self.username:
            raise ProviderUnavailable(
                f"no WRDS username. Add an entry to {pgpass_path()} of the form "
                f"{WRDS_HOST}:{WRDS_PORT}:wrds:<user>:<password>, or set "
                "TRACER_WRDS_USERNAME in .env."
            )

        try:
            self._db = wrds_lib.Connection(wrds_username=self.username)
        except Exception as exc:
            raise ProviderUnavailable(f"cannot connect to WRDS: {exc}") from exc

        logger.info("[data_pulling] wrds connected as %s", self.username)
        return self._db

    def close(self) -> None:
        """Close the connection."""
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None

    def healthcheck(self) -> bool:
        try:
            self._connect().raw_sql("select 1")
            return True
        except Exception:
            return False

    def _permno(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> int:
        """Map a ticker to the PERMNO that carried it during the window.

        No securitysubtype/issuertype filter here on purpose: the usual equity
        screen (securitysubtype='COM', issuertype in ('ACOR','CORP')) would
        exclude every ETF, and ETFs are the whole ROME universe.
        """
        # wrds.raw_sql passes params straight to psycopg2, so placeholders are
        # pyformat (%(name)s), not SQLAlchemy's :name.
        sql = (
            f"select permno, secinfostartdt, secinfoenddt from {self.info_table} "
            "where upper(ticker) = %(ticker)s "
            "  and (secinfostartdt is null or secinfostartdt <= %(end)s) "
            "  and (secinfoenddt is null or secinfoenddt >= %(start)s)"
        )
        try:
            frame = self._connect().raw_sql(
                sql, params={"ticker": symbol, "start": start.date(), "end": end.date()}
            )
        except Exception as exc:
            raise ProviderUnavailable(f"CRSP name lookup failed for {symbol}: {exc}") from exc

        if frame is None or frame.empty:
            raise SymbolNotFound(
                f"no CRSP PERMNO for {symbol} between {start.date()} and {end.date()}"
            )

        permnos = frame["permno"].unique()
        if len(permnos) > 1:
            logger.warning(
                "[data_pulling] wrds: %s maps to %d PERMNOs in this window (%s); using the first",
                symbol, len(permnos), list(permnos),
            )
        return int(permnos[0])

    def _fetch_raw(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        permno = self._permno(symbol, start, end)
        sql = (
            "select dlycaldt as date, dlyopen as open, dlyhigh as high, dlylow as low, "
            "dlyclose as close, dlyprc as prc, dlyret as ret, dlyvol as volume "
            f"from {self.daily_table} "
            "where permno = %(permno)s and dlycaldt between %(start)s and %(end)s "
            "order by dlycaldt"
        )
        try:
            frame = self._connect().raw_sql(
                sql, params={"permno": permno, "start": start.date(), "end": end.date()}
            )
        except Exception as exc:
            raise ProviderUnavailable(
                f"CRSP daily query failed for {symbol} (permno {permno}): {exc}"
            ) from exc

        if frame is None or frame.empty:
            raise CoverageError(
                f"CRSP has no rows for {symbol} between {start.date()} and {end.date()}"
            )
        return self._build_adjusted(frame, symbol)

    @staticmethod
    def _build_adjusted(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Compound dlyret into an index anchored to the final close."""
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"])

        # CRSP encodes a bid/ask midpoint (no trade that day) as a negative
        # price; the magnitude is still the best estimate.
        for column in ("close", "prc"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce").abs()

        if frame.get("close") is None or frame["close"].isna().all():
            frame["close"] = frame.get("prc")

        returns = pd.to_numeric(frame["ret"], errors="coerce").fillna(0.0)
        returns.iloc[0] = 0.0  # first row's return predates the window
        growth = (1.0 + returns).cumprod()

        anchor = frame["close"].last_valid_index()
        if anchor is None:
            raise CoverageError(f"CRSP rows for {symbol} have no usable close to anchor on")
        frame["adj_close"] = growth / growth.loc[anchor] * float(frame["close"].loc[anchor])

        for column in ("open", "high", "low", "volume"):
            if column not in frame.columns:
                frame[column] = np.nan

        return frame[["date", "open", "high", "low", "close", "adj_close", "volume"]]
