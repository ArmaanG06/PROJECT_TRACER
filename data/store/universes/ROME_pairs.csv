"""Candidate pair list — the universe of pairs ROME is allowed to consider.

- Loads my hand-picked candidate pairs, each with a written economic rationale.
- NEVER brute-force combinations. Data-mined pairs do not survive out of sample.
- Records the candidate count. That number is the multiple-testing denominator
  for every p-value reported downstream.
- Output: list of (symbol_a, symbol_b, rationale).
- Symbols must exist in ROME_constituents.csv; fail loudly if one does not.
"""
