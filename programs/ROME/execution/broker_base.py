"""The broker interface — the ONLY thing that differs between backtest and live.

- One method: rebalance(targets, t).
- Diffs the target positions against current holdings and sends only the
  difference. The engine never speaks in buys and sells, only in targets.
- IDEMPOTENT: sending the same targets twice must produce zero extra trades.
  This is what makes a crashed-and-restarted live run safe.
- Also exposes current holdings, so the runner can reconcile.
- sim_broker and ibkr_broker both implement this and nothing else.
"""
