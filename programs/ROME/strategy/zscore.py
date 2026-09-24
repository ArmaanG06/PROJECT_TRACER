"""Standardise the spread into a tradable z-score.

- z = (s - rolling mean) / rolling std, computed on data <= t only.
- OLS mode: the rolling mean absorbs spread drift.
- Kalman mode: alpha_t already absorbs drift, so the rolling mean is near zero.
- NEVER detrend twice. Pick one mechanism per run and record which.
- zscore_lookback is a free parameter: pre-register it before the holdout.
- Output: the z series aligned to the spread, NaN until the window fills.
"""
