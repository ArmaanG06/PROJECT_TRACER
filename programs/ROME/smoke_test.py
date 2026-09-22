"""ROME smoke test: proves the data layer is importable from inside a program.

    python programs/ROME/smoke_test.py          # offline checks
    python programs/ROME/smoke_test.py --live   # also pulls two symbols

No sys.path manipulation here, and there must never be any. The import works
because `pip install -e .` maps `data_pulling` onto data/data_pulling/.
"""

from __future__ import annotations

import sys

from data_pulling import configure_logging, failover_chain, get_prices, load_universe, to_wide

configure_logging("INFO")

universe = load_universe("ROME")
print(f"ROME universe: {len(universe)} symbols in {universe['group'].nunique()} groups")
print(universe.groupby("group")["symbol"].apply(lambda s: " ".join(sorted(s))).to_string())
print(f"\nFailover chain from 'wrds': {' -> '.join(failover_chain('wrds'))}")

if "--live" in sys.argv:
    prices = get_prices(["GLD", "GDX"], "2020-01-01", source="ibkr")
    print(f"\nPulled {len(prices):,} rows")
    print(prices.groupby("symbol")["source"].unique().to_string())
    print(to_wide(prices).tail())
else:
    print("\nOffline checks passed. Re-run with --live to pull data.")
