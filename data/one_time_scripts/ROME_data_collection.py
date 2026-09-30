"""One-time pull of the whole ROME universe into data/store/ROME.duckdb.

Run this once (or again whenever you want to top up / re-pull), then read the
database directly from the program instead of hitting the vendors again:

    python data/one_time_scripts/ROME_data_collection.py
    python data/one_time_scripts/ROME_data_collection.py --source wrds --end 2025-12-31
    python data/one_time_scripts/ROME_data_collection.py --refresh

Later, from anywhere:

    from data_pulling import connect
    prices = connect("ROME").execute("SELECT * FROM prices WHERE symbol='GLD'").df()

Notes before you run it:
  * IBKR needs TWS or IB Gateway open on the port in configs.yaml (7497).
  * WRDS/CRSP runs months behind, so an open-ended request fails its coverage
    check and falls through to the next source. Pass --end to use WRDS.
  * mode="per_symbol" so one dead ticker does not drag the other 41 to a worse
    source. Each symbol still comes from exactly one source; the `source`
    column records which.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from utils import load_config

configs = load_config()

# Lets this run even if `pip install -e .` has not been done in the active
# interpreter. Harmless when it has.
sys.path.append(str(Path(__file__).resolve().parents[1]))  # data/
sys.path.append(str(Path(__file__).resolve().parents[2]))  # repo root, for utils.py

from data_pulling import (  # noqa: E402
    DataUnavailableError,
    cache_status,
    close_db,
    configure_logging,
    db_path,
    get_prices,
    load_symbols,
)


def main(PROGRAM) -> int:
    parser = argparse.ArgumentParser(description="Pull the ROME universe into ROME.duckdb.")
    parser.add_argument("--source", default=configs["data"]["default_provider"], help="Preferred source (default: ibkr)")
    parser.add_argument("--start", default=configs["data"]["start"], help="Start date")
    parser.add_argument("--end", default=configs["data"]["end"], help="Omit for latest available")
    parser.add_argument("--refresh", action="store_true",
                        help="Ignore what is already stored and re-pull everything")
    parser.add_argument("--mode", default="per_symbol", choices=["strict", "per_symbol"])
    args = parser.parse_args()

    configure_logging()
    symbols = load_symbols(PROGRAM)
    print(f"Pulling {len(symbols)} {PROGRAM} symbols from {args.source} "
          f"({args.mode}) starting {args.start} -> {db_path(PROGRAM)}")

    try:
        prices = get_prices(
            symbols,
            args.start,
            args.end,
            source=args.source,
            mode=args.mode,
            refresh=args.refresh,
            db=PROGRAM,
        )
    except DataUnavailableError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        close_db()

    print(f"\nWrote {len(prices):,} rows for {prices['symbol'].nunique()} symbols, "
          f"{prices['date'].min().date()} to {prices['date'].max().date()}")

    status = cache_status(PROGRAM)
    print(f"\n{PROGRAM}.duckdb now holds {len(status)} symbols, "
          f"{status['rows'].sum():,} rows")
    print(status.groupby("source")["symbol"].count().to_string())

    missing = sorted(set(symbols) - set(status["symbol"]))
    if missing:
        print(f"\nNot stored ({len(missing)}): {', '.join(missing)}")

    close_db()
    return 0


if __name__ == "__main__":
    main("ROME")
