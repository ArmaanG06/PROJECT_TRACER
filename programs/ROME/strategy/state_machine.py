"""Per-pair trade state: when to enter, when to get out.

- States: FLAT -> LONG_SPREAD or SHORT_SPREAD once |z| >= entry_z.
- Three exits: z crosses exit_z (take profit), |z| >= stop_z (stop),
  held longer than time_stop_mult x half-life (time stop).
- Exit decisions use the ENTRY-beta spread — the position actually held.
- Breakdown: a rolling ADF that fails k consecutive checks triggers the
  configured action, force_close or hold. The toggle exists so both can be
  measured; do not assume force_close is better.
- No re-entry on the same bar as an exit.
- EXIT-ONLY pairs (dropped by formation) can close but never open.
- Output: the state transition plus which exit fired, for the report's exit mix.
"""
