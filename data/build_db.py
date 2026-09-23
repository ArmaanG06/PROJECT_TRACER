"""Create or rebuild a program's DuckDB file.

The .duckdb files are gitignored (too large), so this script plus
data/schema.sql is what lets anyone recreate the database from scratch.

    python data/build_db.py ROME                     # empty db, schema only
    python data/build_db.py ROME --fill              # + pull the whole universe
    python data/build_db.py ROME --fill --source wrds --start 2015-01-01 --end 2025-12-31
    python data/build_db.py ROME --show              # what's in it

Filling is just get_prices() over the universe, so it obeys the usual failover
(ibkr -> wrds -> yfinance) and writes straight into the database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # so this runs uninstalled

from data_pulling import (  # noqa: E402
    DataUnavailableError,
    cache_status,
    configure_logging,
    connect,
    db_path,
    get_prices,
    load_symbols,
)


def build(program: str, *, fill: bool, source: str, start: str, end: str | None,
          mode: str) -> None:
    """Create the database and optionally fill it from the universe."""
    path = db_path(program)
    existed = path.exists()

    connect(program)  # creates the file and applies data/schema.sql
    print(f"{'Opened' if existed else 'Created'} {path}")

    if not fill:
        print("Schema only. Re-run with --fill to pull data.")
        return

    symbols = load_symbols(program)
    print(f"Filling from universe {program}: {len(symbols)} symbols "
          f"from {source} ({mode}) starting {start}…")
    try:
        prices = get_prices(symbols, start, end, source=source, mode=mode,
                            refresh=True, db=program)
    except DataUnavailableError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Wrote {len(prices):,} rows, {prices['symbol'].nunique()} symbols, "
          f"{prices['date'].min().date()} to {prices['date'].max().date()}")


def show(program: str) -> None:
    """Print what the database currently holds."""
    path = db_path(program)
    if not path.exists():
        print(f"No database at {path}")
        return

    status = cache_status(program)
    size_mb = path.stat().st_size / 1e6
    print(f"{path}  ({size_mb:.1f} MB)\n")
    if status.empty:
        print("Empty -- schema only.")
        return

    print(status.to_string(index=False))
    print(f"\n{len(status)} symbols, {status['rows'].sum():,} rows total")
    print("By source:")
    print(status.groupby("source")["symbol"].count().to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("program", nargs="?", default="ROME",
                        help="Program name, e.g. ROME (default: ROME)")
    parser.add_argument("--fill", action="store_true", help="Pull the universe into the db")
    parser.add_argument("--show", action="store_true", help="Show what the db holds, then exit")
    parser.add_argument("--source", default="ibkr", help="Preferred source (default: ibkr)")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default=None, help="Omit for latest available")
    parser.add_argument("--mode", default="per_symbol", choices=["strict", "per_symbol"],
                        help="per_symbol lets each symbol fail over alone (default)")
    args = parser.parse_args()

    configure_logging()
    program = args.program.upper()

    if args.show:
        show(program)
        return

    build(program, fill=args.fill, source=args.source, start=args.start,
          end=args.end, mode=args.mode)
    show(program)


if __name__ == "__main__":
    main()
