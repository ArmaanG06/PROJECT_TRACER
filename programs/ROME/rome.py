"""ROME — ETF pairs trading.

THIS IS WHERE STRATEGY CODE GOES. Everything about ROME lives in this folder:
signals, pair selection, backtest, sizing. Add files here as it grows, e.g.

    programs/ROME/
        rome.py          this file — entry point
        pairs.py         pair selection
        signals.py       spread / z-score logic
        backtest.py
        notes.md

Nothing outside programs/ROME/ should need to change to build the strategy.
Data comes in through one import; it does not care which vendor served it.

    python programs/ROME/rome.py
"""

from data_pulling import configure_logging, get_prices, load_symbols, to_wide

UNIVERSE = "ROME"
START = "2010-01-01"
SOURCE = "ibkr"


def load_prices():
    """Pull the ROME universe as a date x symbol frame of adjusted closes."""
    symbols = load_symbols(UNIVERSE)
    prices = get_prices(symbols, START, source=SOURCE, mode="per_symbol")
    return to_wide(prices, "adj_close")


def main() -> None:
    configure_logging()
    closes = load_prices()
    print(f"{closes.shape[1]} symbols, {closes.shape[0]} days")
    print(closes.tail())

    # --- strategy starts here -------------------------------------------
    # pairs  = select_pairs(closes)
    # signal = zscore(spread(closes, pairs))
    # ...


if __name__ == "__main__":
    main()
