"""Monthly formation — decides which candidate pairs are currently tradable.

- Input: prices up to t ONLY. Output: active pairs with beta, half-life, spread sigma.
- OLS on LOG prices gives beta. Cointegration via Engle-Granger with trend="ct",
  judged against MacKinnon critical values — NOT a plain ADF on the residual.
- Trending spreads are allowed. Estimate the OU half-life on the DETRENDED
  residual, otherwise the drift inflates it.
- Filters: 1 <= half-life <= 30 days. Expected reversion (entry_z x sigma) must
  exceed 3x round-trip cost across BOTH legs.
- Rank the survivors, keep top_n.
- A pair that drops out while a trade is open becomes EXIT-ONLY: no new entries,
  existing position still managed.
"""
