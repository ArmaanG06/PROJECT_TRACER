# Project Tracer

Personal systematic trading book. Each algo lives in `programs/<CITY>/`; the
data layer is shared. First algo: **ROME** — ETF pairs trading over a 42-name
universe.

```
config/settings.yaml          providers, paths, strategy registry
data/
  data_pulling/
    __init__.py               the puller: get_prices, failover, store, universes
    ibkr.py  wrds.py  yfinance.py     one file per source
  schema.sql                  database schema (committed)
  build_db.py                 create/rebuild a program database
  store/
    universes/ROME_constituents.csv
    ROME.duckdb               one database per program (gitignored)
programs/ROME/rome.py         strategy code goes here
command_center/mockup.html    visual mockup — just open it in a browser
```

## Setup

```bash
venv/Scripts/python -m pip install -e .
```

That mapping is what makes `from data_pulling import get_prices` work from
`programs/ROME/` — or any other folder. Paths inside the package resolve off
the repo root, found by walking up from the package file itself, so they never
depend on where you run from. (`rome.py` also appends `data/` to `sys.path` as
a belt-and-braces fallback, so the import works even before you install.)

**Use the venv's interpreter.** There are several Pythons on this machine and
`python` resolves to `C:\Python314`, which has none of these packages.
`.vscode/settings.json` pins VSCode to `venv/Scripts/python.exe` so Run/Debug
and new terminals get the right one. From a shell, call it explicitly:
`venv/Scripts/python programs/ROME/rome.py`.

**Re-run `pip install -e .` if you move, rename or copy the project folder, or
rebuild the venv.** The editable install writes your absolute path into
`venv/Lib/site-packages/__editable___project_tracer_*_finder.py`, and that path
goes stale. `ModuleNotFoundError: No module named 'data_pulling'` means this.

`project_tracer.egg-info/` is throwaway build metadata; it is gitignored, safe
to delete, and regenerated on each install.

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

## The database

Prices live in one DuckDB file per program — `data/store/ROME.duckdb` — holding
a `prices` table and a `meta` table (source, date range, row count, adjustment
method, last pull) for every symbol.

**One name per program.** A program called ROME means `programs/ROME/`,
`ROME_constituents.csv` and `ROME.duckdb`. Nothing in config restates that link,
and there is no global "default database" — the database belongs to the program,
so the caller names it: `get_prices(..., db="ROME")`. Omit `db` and nothing is
stored; the data comes straight from the provider.

The `.duckdb` files are **not committed** (too large). Two committed files let
anyone recreate them:

- `data/schema.sql` — the table definitions, applied automatically on first
  connect. The one place the shape of the data is written down.
- `data/build_db.py` — creates and fills a database. It takes the program name
  as an argument, so it serves every program, not just ROME.

```bash
python data/build_db.py ROME --fill              # schema + pull the universe
python data/build_db.py ROME --show              # what's in it
python data/build_db.py OSLO --fill              # a future program, same script
python data/build_db.py ROME --fill --source wrds --start 2015-01-01 --end 2025-12-31
```

`meta`'s primary key is `symbol` **alone**, deliberately — a symbol physically
cannot hold two sources at once, so the no-mixing rule is enforced by the
database rather than by convention. Writes replace a symbol wholesale.

Query it directly whenever that's easier than going through `get_prices`:

```python
from data_pulling import connect
connect("ROME").execute("SELECT symbol, count(*) FROM prices GROUP BY symbol").df()
```

DuckDB holds a file lock, so call `close_db()` when a script finishes if you
want to open the database elsewhere.

## Writing a strategy

Everything for an algo goes in its own folder. Start from
[programs/ROME/rome.py](programs/ROME/rome.py) and add files beside it
(`pairs.py`, `signals.py`, `backtest.py`). Nothing outside that folder needs to
change. Register it in the `strategies:` block of `config/settings.yaml`.

## Command center

Open `command_center/mockup.html` in a browser. Static HTML with hardcoded
numbers — layout only, nothing connected, no server and no dependencies.

## Provider notes

- **IBKR** — `ib_async`, read-only connection to TWS/Gateway. `ADJUSTED_LAST`
  gives `adj_close`, `TRADES` gives raw OHLCV. `ADJUSTED_LAST` requires a blank
  `endDateTime` (an explicit end date returns error 162), so it requests a full
  duration and trims locally.
- **WRDS/CRSP** — CIZ tables (`crsp.dsf_v2`, `crsp.stksecurityinfohist`). The
  legacy SIZ tables are end-of-life; Dec-2024 was the last release in that
  format. `adj_close` is a total-return index compounded from `dlyret` and
  anchored to the final close. **CRSP runs months behind** (currently ends
  2025-12-31), so an open-ended request always fails its coverage check and
  falls through to the next source — pass an explicit `end` to use WRDS.
- **yfinance** — last resort, warns on every use. `auto_adjust=False` is passed
  explicitly because yfinance flipped that default, and under the new one
  `Adj Close` disappears and `Close` is overwritten with the adjusted series.
