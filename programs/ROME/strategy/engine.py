"""The daily engine: turns today's data into TARGET positions for every pair.

Called once per day by runner.run(). The runner and this file are the ONLY two places where
pipeline stages are wired together; the stage files (spread, zscore, breakdown, signals,
sizing, kalman) never import each other.

SKELETON: every NOT BUILT line is pseudocode until that stage exists.
"""
import pandas as pd

from ROME.models import PairSpec

# ---- NOT BUILT YET ---------------------------------------------------------
# from ROME.strategy.spread import pair_spread
# from ROME.strategy.kalman import kalman_update
# from ROME.strategy.zscore import zscore
# from ROME.strategy.breakdown import is_broken
# from ROME.strategy.signals import next_action
# from ROME.strategy.sizing import target_shares


def decide_targets(data: pd.DataFrame, specs: list[PairSpec], state, rome: dict):
    """For every pair we trade or hold: hedge -> spread -> z-score -> breakdown -> signal -> size.

    data:  prices up to and including today (the runner has already cut off the future)
    specs: this month's PairSpecs from formation
    state: strategy memory (open trades, frozen betas, Kalman values, breakdown counts)
    rome:  the strategies.ROME config section

    Returns (targets, state):
        targets = {pair_id: target shares for each leg}  -> runner turns these into orders
        state   = updated strategy memory                -> runner saves it
    """
    targets = {}

    for pair in pairs_to_manage(specs, state):
        # 1. which hedge ratio to use
        beta, alpha = hedge_for(pair, data, state, rome)

        # 2. the gap between the legs: log_a - alpha - beta * log_b
        spread = pair_spread(data, pair.a, pair.b, beta, alpha)                     # NOT BUILT

        # 3. how stretched is it?  (solve the drift-lag bias here, see CLAUDE.md)
        z = zscore(spread, rome["signal"]["zscore_lookback"])                       # NOT BUILT

        # 4. has an OPEN pair stopped behaving like a pair?  (k fails in a row, counts kept in state)
        broken, state = is_broken(pair, data, state, rome["breakdown"])             # NOT BUILT

        # 5. what to do: enter long/short, take profit, stop, time stop, force-close, or hold
        action = next_action(z, pair, state, broken, rome["signal"], rome["breakdown"])  # NOT BUILT

        # 6. how many shares of each leg we WANT to hold after tomorrow's open (0 = flat)
        targets[pair.pair_id] = target_shares(pair, action, spread, data, rome["sizing"])  # NOT BUILT

    return targets, state


def pairs_to_manage(specs: list[PairSpec], state) -> list:
    """Which pairs need a decision today.

    = this month's SELECTED pairs (may open a new trade)
    + every pair with an OPEN trade, even if it dropped out at refit (exit-only: may only close)
    Each pair appears once.
    """
    # NOT BUILT
    #   selected = [spec for spec in specs if spec.selected]
    #   open_pairs = pairs in state with an open trade
    #   return selected + open pairs not already in selected
    pass


def hedge_for(pair, data: pd.DataFrame, state, rome: dict) -> tuple[float, float]:
    """Which beta and alpha to build today's spread with.

    OPEN trade -> its FROZEN entry beta/alpha from state (exit checks must use the entry beta)
    NEW entry  -> depends on config hedge.method:
                    "ols"    -> the beta/alpha from this month's formation (pair.beta, pair.alpha)
                    "kalman" -> today's Kalman beta/alpha (kalman_update, values kept in state)
    """
    # NOT BUILT
    #   if pair has an open trade in state:
    #       return state's frozen entry beta, alpha
    #   if rome["hedge"]["method"] == "ols":
    #       return pair.beta, pair.alpha
    #   if rome["hedge"]["method"] == "kalman":
    #       beta, alpha = kalman_update(...)     # also update Kalman P in state
    #       return beta, alpha
    pass
