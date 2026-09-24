"""The loop that drives everything. The only place that knows the mode.

- Per day: refit formation if due -> engine.step -> broker.rebalance.
- Mode comes from config and picks the broker. Nothing else changes.
- Walk-forward IS this loop: formation only ever sees data <= t, so there is no
  separate walk-forward harness.
- The price feed must expose data <= t only and RAISE on any future access.
  That guarantee is what the look-ahead test verifies.
- Splits: train 2012-2019, validate 2020-2022, holdout 2023-now.
  The holdout runs ONCE, after every TBD is pinned.
- Loads prices via `from data_pulling import get_prices` (db="ROME"), once at
  startup, then slices — it does not re-query per day.
- Writes state through state_store after each step, and hands the ledger to
  report at the end.
"""
