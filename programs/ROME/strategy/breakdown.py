import pandas as pd

from ROME.strategy.stats import adf_pvalue


def is_broken(spread: pd.Series, fail_count: int, days_open: int, breakdown_cfg: dict, trend: str, autolag: str):
    window = breakdown_cfg["window"]
    fail_p = breakdown_cfg["pvalue"]
    fails_needed = breakdown_cfg["consecutive_fails"]
    check_every = breakdown_cfg["check_every_days"]

    if days_open % check_every != 0:
        broken = fail_count >= fails_needed
        return broken, fail_count

    if len(spread) < window:
        broken = fail_count >= fails_needed
        return broken, fail_count

    last_window = spread.iloc[-window:]
    p = adf_pvalue(last_window, trend, autolag)

    if p >= fail_p:
        fail_count = fail_count + 1
    else:
        fail_count = 0

    broken = fail_count >= fails_needed
    return broken, fail_count
