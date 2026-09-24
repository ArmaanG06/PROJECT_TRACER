"""What actually happened — per pair and in total.

- Metrics: P&L, Sharpe, max drawdown, hit rate, average hold vs half-life,
  cost drag, and the exit-type mix (profit / stop / time / breakdown).
- Average hold vs half-life is the honesty check: if holds run far past the
  estimated half-life, the formation filter is not measuring what it claims.
- Cost drag shown as a share of gross P&L, so a strategy that only works
  pre-cost is obvious.
- Compares runs side by side: OLS vs Kalman, breakdown force_close vs hold.
- Every run logs its config hash + variant ID. A result without one does not
  count, because it cannot be reproduced.
- Counts candidate pairs from pairs.py alongside any p-value, so the
  multiple-testing burden is always visible.
"""
