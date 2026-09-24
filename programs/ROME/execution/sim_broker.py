"""Simulated broker for backtests.

- Fills at the NEXT OPEN's actual price, including gaps. A 3.5-sigma stop can
  and will fill at 4.5 sigma; the backtest must show that, not the stop level.
- Never fills at the signal bar's close. That would be look-ahead.
- Applies costs.py to every fill — no free trades.
- Keeps the ledger: fills, holdings, cash, realised and unrealised P&L.
- A target it cannot fill (halt, no volume) is logged and left unfilled rather
  than silently assumed.
"""
