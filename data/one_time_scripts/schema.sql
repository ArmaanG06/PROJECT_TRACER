-- Schema for a program's price database: data/store/<PROGRAM>.duckdb
-- One database per program (ROME.duckdb, OSLO.duckdb, ...).
--
-- The .duckdb files are NOT committed (too large). Recreate one with:
--     python data/build_db.py ROME --fill

CREATE TABLE IF NOT EXISTS prices (
    symbol    VARCHAR NOT NULL,
    date      DATE    NOT NULL,
    open      DOUBLE,
    high      DOUBLE,
    low       DOUBLE,
    close     DOUBLE,
    adj_close DOUBLE,           -- total-return adjusted (splits + dividends)
    volume    DOUBLE,
    source    VARCHAR NOT NULL, -- ibkr | wrds | yfinance
    PRIMARY KEY (symbol, date)
);

-- One row per symbol, holding provenance for the series in `prices`.
--
-- The PRIMARY KEY is on symbol ALONE, deliberately: it makes the no-mixing
-- rule structural. A symbol physically cannot have two sources at once, so
-- there is no way to end up with half a series from IB and half from Yahoo.
-- Writes replace a symbol wholesale rather than appending.
CREATE TABLE IF NOT EXISTS meta (
    symbol     VARCHAR NOT NULL PRIMARY KEY,
    source     VARCHAR NOT NULL,
    start_date DATE,
    end_date   DATE,
    rows       BIGINT,
    adjustment VARCHAR,         -- how adj_close was produced by that source
    pulled_at  TIMESTAMP
);
