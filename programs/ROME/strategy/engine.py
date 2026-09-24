"""The daily decision step — the whole strategy behind one function.

- step(state, bar_t, active_pairs) -> (new_state, target_positions).
- A PURE function: same inputs always give the same outputs, no I/O, no clock,
  no network. That is what makes the look-ahead and parity tests possible.
- Identical code path for backtest and live. Nothing here knows which it is.
- Sequence per pair: spread -> zscore -> state_machine -> sizing.
- State must be serializable (state_store writes it to disk between live runs)
  and must carry each open trade's frozen entry beta.
- Reads no config at call time; parameters arrive as arguments.
"""
