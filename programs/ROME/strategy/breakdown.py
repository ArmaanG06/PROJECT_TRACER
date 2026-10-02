import pandas as pd

from ROME.strategy.stats import adf_pvalue


def is_broken(spread: pd.Series, fail_count: int, days_open: int, breakdown_cfg: dict, trend: str, autolag: str):
    window = breakdown_cfg["window"]
    fail_p = breakdown_cfg["pvalue"]
    fails_needed = breakdown_cfg["consecutive_fails"]
    check_every = breakdown_cfg["check_every_days"]

    # 1. only test on check days (weekly). other days: nothing changes
    if days_open % check_every != 0:
        broken = fail_count >= fails_needed
        return broken, fail_count

    # 2. not enough history to judge: nothing changes (never counts as a fail)
    if len(spread) < window:
        broken = fail_count >= fails_needed
        return broken, fail_count

    # 3. test the last `window` days
    last_window = spread.iloc[-window:]
    p = adf_pvalue(last_window, trend, autolag)

    # 4. a fail adds to the streak, a pass resets it (the fails must be IN A ROW)
    if p >= fail_p:
        fail_count = fail_count + 1
    else:
        fail_count = 0

    broken = fail_count >= fails_needed
    return broken, fail_count
