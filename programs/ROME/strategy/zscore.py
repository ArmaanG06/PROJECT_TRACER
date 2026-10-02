# z = (todays spread - avg of previous n days) / std dev of prevous n days

import pandas as pd

def zscore(spread: pd.Series, N: int):
    shifted_spread = spread.shift(1)
    rolling_avg = shifted_spread.rolling(N).mean()
    rolling_std = shifted_spread.rolling(N).std()

    # a std of 0 means the spread didn't move at all for N days: there is no "normal wiggle" to
    # measure against, so z is undefined. NaN (= no signal) instead of dividing by 0 -> infinity.
    rolling_std = rolling_std.replace(0, float("nan"))

    z = (spread - rolling_avg) / rolling_std
    return z