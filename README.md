# Project Tracer

A personal systematic trading book. Algos live in `programs/<CITY>/`; the data
layer and command center are shared across all of them.

First algo: **ROME** — ETF pairs trading across a 42-name universe of commodity,
rates, credit, sector, international and FX proxies.

## Quickstart

```bash
# 1. Install (editable, so `data_pulling` imports from anywhere)
venv/Scripts/python -m pip install -e .

# 2. Credentials
cp .env.example .env          # IBKR host/port; WRDS username
# WRDS password goes in pgpass, never in .env:
#   Windows  %APPDATA%\postgresql\pgpass.conf
#   Linux    ~/.pgpass   (chmod 600)
#   Format   wrds-pgdata.wharton.upenn.edu:9737:wrds:<user>:<password>

# 3. Check it works
python programs/ROME/smoke_test.py
tracer data health
```

## Pulling data

```bash
tracer data pull --universe ROME --source ibkr --start 2010-01-01
tracer data status
```

From Python, anywhere in the repo:

```python
from data_pulling import get_prices, to_wide, load_universe

prices = get_prices(["GLD", "GDX"], "2010-01-01", source="ibkr")
closes = to_wide(prices, "adj_close")
symbols = load_universe("ROME")["symbol"].tolist()
```

`adj_close` is total-return adjusted. Every symbol's series comes from exactly
one source — recorded in the `source` column — and ranges are never spliced
across vendors. See [CLAUDE.md](CLAUDE.md) for the full contract.

Sources are tried `ibkr → wrds → yfinance`, starting from whichever you asked
for. Each switch prints a warning saying what failed and why.

## Command center

```bash
tracer data pull --universe ROME [--source ibkr] [--start ...] [--mode strict|per_symbol]
tracer data status        # what's cached: symbol, source, range, staleness
tracer data health        # can we reach TWS, WRDS, Yahoo?
tracer algo list
tracer algo set ROME --status dev|paper|live|off
tracer dashboard          # read-only Streamlit view
```

The dashboard is strictly read-only: cache state, provider health, source mix
per universe, and the strategy registry. No order entry, no positions, nothing
that touches execution.

## Requirements

Python ≥ 3.11. A running TWS or IB Gateway for IBKR data, a WRDS subscription
for CRSP, or neither if you only use yfinance.
