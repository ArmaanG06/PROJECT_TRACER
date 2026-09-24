"""Kalman filter for a time-varying hedge ratio (alternative to rolling OLS).

- Estimates beta_t and alpha_t, where the random-walk intercept absorbs drift.
- State: beta, alpha and the covariance matrix P, carried forward per pair.
- Updates with data <= t only. One update per bar, never a re-fit over history.
- Used for NEW entries only. Open trades keep their frozen entry beta.
- kalman_delta and kalman_obs_var are tuned knobs, so every setting is a
  separate logged variant — they are a live overfitting risk.
- Compare against OLS on the same splits before trusting it.
"""
