"""Persist engine state so a live run survives a restart.

- Live: write engine state + positions to disk after EVERY step; reload on start.
- Backtest: in memory only, no disk I/O.
- Must round-trip exactly — a reloaded state has to produce the same next
  decision as if the process had never stopped. Frozen entry betas included.
- On startup, compare the loaded positions against the broker's actual holdings
  and refuse to trade on a mismatch rather than guessing.
- Plain serializable format (JSON) so a stuck state can be read and fixed by hand.
"""
