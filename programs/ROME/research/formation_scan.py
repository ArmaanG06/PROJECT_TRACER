import warnings
from dataclasses import asdict
from pathlib import Path

import duckdb
import pandas as pd

from utils.utils import get_project_root, load_config
from ROME.strategy.formation import form_pairs

def load_prices(db_file: Path) -> pd.DataFrame:
    # 1. read the long table: one row per (date, symbol)
    db = duckdb.connect(database=str(db_file), read_only=True)
    long_prices = db.execute("SELECT date, symbol, adj_close FROM prices").df()
    db.close()

    # 2. turn it wide: one row per date, one column per symbol
    wide_prices = long_prices.pivot(index="date", columns="symbol", values="adj_close")

    # 3. make sure the dates are real dates and in order
    wide_prices.index = pd.to_datetime(wide_prices.index)
    wide_prices = wide_prices.sort_index()
    return wide_prices


def refit_dates(prices: pd.DataFrame, start, end) -> list[pd.Timestamp]:
    """The last TRADING day of each month between start and end.

    Uses the dates in prices.index, not a calendar: a month-end that falls on a weekend or
    holiday maps to the last day that actually has data.
    """
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    last_day_of_month = {}
    for day in prices.index:
        if day < start or day > end:
            continue
        month = (day.year, day.month)
        last_day_of_month[month] = day

    return list(last_day_of_month.values())


def scan(prices: pd.DataFrame, pairs: pd.DataFrame, cfg: dict, dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Call form_pairs(prices, t, pairs, cfg) for every t in dates.

    Returns one row per pair per month: every PairSpec field as a column.
    """
    rows = []
    month_number = 0

    for t in dates:
        month_number += 1
        print(f"forming month {month_number} of {len(dates)}: {t.date()}")

        specs = form_pairs(prices, t, pairs, cfg)
        for spec in specs:
            row = asdict(spec)
            rows.append(row)

    results = pd.DataFrame(rows)
    return results


def summarise(results: pd.DataFrame, dates: list[pd.Timestamp]) -> None:
    """Print what the kill/continue call needs."""
    n_months = len(dates)
    n_pairs = results["pair_id"].nunique()
    n_rows = len(results)
    tradable = results[results["status"] == "tradable"]

    print()
    print(f"=== {n_pairs} pairs x {n_months} months = {n_rows} pair-months ===")

    # ---- 1. how often each status happened --------------------------------
    print()
    print("1. Status across all pair-months")
    status_counts = results["status"].value_counts()
    for status, count in status_counts.items():
        share = count / n_rows
        print(f"   {status:18s} {count:6d}   ({share:.1%})")

    # ---- 2. how many pairs were tradable each month -----------------------
    print()
    print("2. Tradable pairs per month")
    tradable_per_month = []
    for t in dates:
        count = (tradable["formed_on"] == t).sum()
        tradable_per_month.append(count)
    per_month = pd.Series(tradable_per_month, index=dates)

    months_with_zero = (per_month == 0).sum()
    print(f"   mean {per_month.mean():.1f} | min {per_month.min()} | max {per_month.max()}")
    print(f"   months with zero tradable pairs: {months_with_zero} of {n_months}")

    print("   average per month, by year:")
    for year in sorted(set(per_month.index.year)):
        this_year = per_month[per_month.index.year == year]
        print(f"   {year}: {this_year.mean():.1f}")

    # ---- 3. pass rate per pair -------------------------------------------
    print()
    print("3. Pass rate per pair (share of months tradable), best first")
    months_tradable = tradable["pair_id"].value_counts()   # already sorted, most first
    for pair_id, count in months_tradable.items():
        rate = count / n_months
        print(f"   {pair_id:10s} {rate:.0%}")

    # ---- 4. pairs that never passed, and why -----------------------------
    print()
    all_pairs = set(results["pair_id"])
    passed_pairs = set(tradable["pair_id"])
    never_passed = sorted(all_pairs - passed_pairs)
    print(f"4. Never tradable: {len(never_passed)} of {n_pairs} pairs")

    for pair_id in never_passed:
        this_pair = results[results["pair_id"] == pair_id]
        most_common_failure = this_pair["status"].value_counts().index[0]
        print(f"   {pair_id:10s} mostly: {most_common_failure}")


def main() -> None:
    configs = load_config()
    rome = configs["strategies"]["ROME"]
    cfg = rome["formation"]
    research = configs["research"]
    root = get_project_root()

    # 1. inputs
    prices = load_prices(root / rome["db"])
    pairs = pd.read_csv(root / cfg["pairs_file"])
    split = research["scan_split"]
    split_start, split_end = rome["splits"][split]
    dates = refit_dates(prices, split_start, split_end)

    print(f"Prices: {prices.shape[1]} symbols, {prices.index.min().date()} to {prices.index.max().date()}")
    print(f"Pairs: {len(pairs)}   Refits: {len(dates)} ({dates[0].date()} to {dates[-1].date()})")

    # 2. run formation every month (statsmodels warns on some odd windows; hide the noise)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        results = scan(prices, pairs, cfg, dates)

    # 3. save the full table so it can be opened in Excel
    output_dir = root / research["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"formation_scan_{split}.csv"
    results.to_csv(out_file, index=False)
    print(f"Saved {out_file}")

    # 4. print the summary
    summarise(results, dates)


if __name__ == "__main__":
    main()
