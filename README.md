# Project Tracer

Personal systematic trading book. Each algo lives in `programs/<CITY>/`; the
data layer is shared. First algo: **ROME** — ETF pairs trading over a 42-name
universe.

```
config/settings.yaml          providers, paths, strategy registry
data/
  data_pulling/
    __init__.py               the puller: get_prices, failover, cache, universes
    ibkr.py  wrds.py  yfinance.py     one file per source
  store/
    universes/ROME_constituents.csv
    cache/<source>/<SYMBOL>.parquet   (gitignored)
programs/ROME/rome.py         strategy code goes here
command_center/mockup.py      visual mockup, not wired up
```

## Setup

```bash
venv/Scripts/python -m pip install -e .
```

That mapping is what makes `from data_pulling import get_prices` work from
`programs/ROME/` with no `sys.path` hacks.

WRDS credentials go in pgpass, never in the repo — on Windows
`%APPDATA%\postgresql\pgpass.conf`, format
`wrds-pgdata.wharton.upenn.edu:9737:wrds:<user>:<password>`. IBKR host/port are
in `config/settings.yaml` (default `127.0.0.1:7497`, TWS paper).

## Use

```python
from data_pulling import get_prices, to_wide, load_symbols

prices = get_prices(["GLD", "GDX"], "2010-01-01", source="ibkr")
closes = to_wide(prices, "adj_close")
symbols = load_symbols("ROME")
```

Returns a tidy long frame: `date, open, high, low, close, adj_close, volume,
symbol, source`. `adj_close` is total-return adjusted (splits and dividends).

Sources are tried `ibkr → wrds → yfinance`, starting from whichever you asked
for. Each switch logs one line saying what failed and why:

```
WARNING [data_pulling] ibkr failed for LQD (reason: cannot reach TWS/Gateway
        at 127.0.0.1:7497 ...) → switched to wrds
```

`mode="strict"` (default) makes the basket atomic — one symbol failing moves
all of them to the next source. `mode="per_symbol"` lets each fail over alone.

**The no-mixing rule:** a symbol's series always comes from exactly one source,
recorded in the `source` column. Ranges are never spliced across vendors —
their adjustment methods and dividend timing differ, so a stitched series shows
a return on the join date that never happened.

## Writing a strategy

Everything for an algo goes in its own folder. Start from
[programs/ROME/rome.py](programs/ROME/rome.py) and add files beside it
(`pairs.py`, `signals.py`, `backtest.py`). Nothing outside that folder needs to
change. Register it in the `strategies:` block of `config/settings.yaml`.

## Command center

```bash
streamlit run command_center/mockup.py
```

A visual mockup with hardcoded numbers — layout only, nothing connected.

## Provider notes

- **IBKR** — `ib_async`, read-only connection to TWS/Gateway. `ADJUSTED_LAST`
  gives `adj_close`, `TRADES` gives raw OHLCV. `ADJUSTED_LAST` requires a blank
  `endDateTime` (an explicit end date returns error 162), so it requests a full
  duration and trims locally.
- **WRDS/CRSP** — CIZ tables (`crsp.dsf_v2`, `crsp.stksecurityinfohist`). The
  legacy SIZ tables are end-of-life; Dec-2024 was the last release in that
  format. `adj_close` is a total-return index compounded from `dlyret` and
  anchored to the final close.
- **yfinance** — last resort, warns on every use. `auto_adjust=False` is passed
  explicitly because yfinance flipped that default, and under the new one
  `Adj Close` disappears and `Close` is overwritten with the adjusted series.
