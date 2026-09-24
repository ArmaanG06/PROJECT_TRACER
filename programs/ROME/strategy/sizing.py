"""Turn trade states into share counts.

- Dollar-neutral per pair; the leg ratio comes from beta.
- Size from SPREAD volatility, not price volatility — the spread is what we hold.
- Each pair risks risk_per_pair of capital.
- Enforce min_notional_per_leg ($1,000). Skip the pair entirely if capital
  cannot support both legs at that floor.
- Respect max_pairs; if more pairs signal than that, rank and take the best.
- Output: TARGET POSITIONS (shares per symbol), not buy/sell signals. Targets
  are absolute, which is what makes the broker idempotent.
- Shares are whole numbers, so record the rounding drift from dollar-neutral.
"""
