"""Live/paper broker — same interface as sim_broker, real orders.

- Implements broker_base.rebalance, so the engine cannot tell the difference.
- Places orders for the next open (market-on-open, or equivalent) to match the
  backtest's fill assumption.
- PAPER ACCOUNT FIRST. Only after parity with the backtest holds.
- Reconciles actual fills against targets, and logs slippage versus the
  next-open price. That number is the honest cost of going live.
- A partial or rejected fill leaves state consistent: re-running rebalance with
  the same targets completes the job rather than doubling it.
- Reuses the TWS connection settings from configs.yaml (data.providers.ibkr).
"""
