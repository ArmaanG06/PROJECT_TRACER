# Project Tracer

Personal systematic trading book. Algos live in `programs/<CITY>/`, named after
world cities. Data code and data files are kept separate from programs so they
stay interchangeable.

## Layout

```
data/
  data_pulling/          all data CODE (imports as `data_pulling`)
    api.py               get_prices() + failover
    providers/           base.py, ibkr.py, wrds.py, yfinance.py
    store.py             parquet cache
    universe.py          universe CSV loader
    config.py, errors.py
  store/                 all data FILES
    universes/ROME_constituents.csv
    cache/<source>/<SYMBOL>.parquet        (gitignored)
command_center/          cli.py (the `tracer` command), dashboard.py, registry.py
config/                  settings.yaml, strategies.yaml
programs/ROME/           first algo: ETF pairs trading
```

## Data API

```python
from data_pulling import get_prices, to_wide, load_universe

get_prices(
    symbols,                    # str | list[str]
    start, end=None,            # end=None -> latest available
    source="ibkr",              # ibkr | wrds | yfinance
    fallback=True,
    mode="strict",              # strict | per_symbol
    use_cache=True,
    refresh=False,
) -> pd.DataFrame
```

Returns a tidy long frame: `date, open, high, low, close, adj_close, volume,
symbol, source`. Dates tz-naive, sorted, unique per symbol. `adj_close` is
total-return adjusted (splits **and** dividends).

Also `to_wide(df, field="adj_close")` and `load_universe("ROME")`.

### Failover

Order is always `ibkr → wrds → yfinance`, starting at `source` and skipping
anything already tried. A failure is a connection/auth error, an empty result,
an unknown symbol, or coverage short of the requested end. Every switch logs
one line:

```
[data_pulling] ibkr failed for XOP (reason: ...) → switched to wrds
```

- `mode="strict"` (default): all symbols come from one source. Any failure
  retries the **whole basket** on the next source. If no single source covers
  it, raises `DataUnavailableError`.
- `mode="per_symbol"`: each symbol fails over on its own; `source` records
  provenance and a WARNING summarises the mix.
- `fallback=False`: raises the first provider error untouched.

### The no-mixing rule

**A symbol's series always comes from exactly one source. Date ranges are never
spliced across sources.** If IB covers 2010–2020 and Yahoo covers 2020–2026,
the answer is not "both" — it is "IB failed, use Yahoo for all of it", or an
error. Vendors' adjustment methods and dividend timing do not line up, so a
stitched series produces a return on the join date that never happened. The
cache is keyed on `(source, symbol)` so the two can never overwrite each other.

## Provider notes

- **IBKR** — `ib_async`, connects read-only to TWS/Gateway (default
  `127.0.0.1:7497`, paper). `ADJUSTED_LAST` gives `adj_close`, `TRADES` gives
  raw OHLCV. `ADJUSTED_LAST` **requires a blank `endDateTime`** (an explicit end
  date returns error 162), so the provider requests a full duration and trims
  locally. Paced to respect TWS's 60-requests-per-10-minutes limit.
- **WRDS/CRSP** — CIZ tables (`crsp.dsf_v2`, `crsp.stksecurityinfohist`). The
  legacy SIZ tables (`crsp.stocknames`, `crsp.dsf`) are end-of-life: Dec-2024
  data was the last release in that format. Ticker → PERMNO is resolved as of
  the query window, since tickers get reused. `adj_close` is a total-return
  index compounded from `dlyret` and anchored to the final close. Credentials
  come from pgpass only — on Windows that is
  `%APPDATA%\postgresql\pgpass.conf`, **not** `~/.pgpass`.
- **yfinance** — last resort, logs a WARNING on every use. `auto_adjust=False`
  is passed explicitly because yfinance flipped that default; under the new
  default `Adj Close` disappears and `Close` is silently overwritten with the
  adjusted series.

## Install / run

```bash
venv/Scripts/python -m pip install -e .     # editable; makes `data_pulling` importable anywhere
python programs/ROME/smoke_test.py          # offline check

tracer data pull --universe ROME --source ibkr --start 2010-01-01
tracer data status
tracer data health
tracer algo list
tracer algo set ROME --status paper         # edits config/strategies.yaml only
tracer dashboard                            # read-only Streamlit
```

No `sys.path` manipulation anywhere — `pyproject.toml` maps the import name
`data_pulling` onto `data/data_pulling/`.
