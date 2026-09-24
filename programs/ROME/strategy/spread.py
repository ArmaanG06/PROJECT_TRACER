"""The spread series for a pair.

- s_t = log(A) - beta * log(B) - alpha.
- An OPEN trade computes its spread with its FROZEN entry beta — the position
  actually held, not a re-estimated one.
- New entries use the current beta (OLS from formation, or beta_t from Kalman).
- Consequence: two pairs on the same symbols can carry different betas at once,
  one frozen and one live. That is intended.
- Input: prices <= t plus the beta/alpha to use. Output: the spread series.
"""
