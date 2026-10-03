"""The daily engine: turns today's data into TARGET positions for every pair.

Called once per day by runner.run(). The runner and this file are the ONLY two places where
pipeline stages are wired together; the stage files (spread, zscore, breakdown, signals,
sizing, kalman) never import each other.

SKELETON: every NOT BUILT line is pseudocode until that stage exists.
"""
import pandas as pd

from ROME.models import PairSpec
from ROME.strategy.spread import pair_spread
from ROME.strategy.zscore import zscore
from ROME.strategy.breakdown import is_broken
from ROME.strategy.signals import levels, next_action
from ROME.strategy.costs import round_trip_cost          # toolbox: today's cost for cost_aware levels


# ---- NOT BUILT YET ---------------------------------------------------------
# from ROME.strategy.kalman import kalman_update
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
        spread = pair_spread(data, pair.a, pair.b, beta, alpha)

        # 3. how stretched is it today?  (option A: today vs the previous N days, see CLAUDE.md)
        z = zscore(spread, rome["signal"]["zscore_lookback"])

        # only TODAY's z matters for the decision. If either leg has no price today, the spread's
        # last date is an older day, so there is no fresh z: treat it as "no signal" (NaN).
        today = data.index[-1]
        if spread.index[-1] == today:
            z_today = z.iloc[-1]
        else:
            z_today = float("nan")

        # 4. has an OPEN pair stopped behaving like a pair?  (weekly test, k fails in a row)
        #    only open trades are tested; `spread` above already uses the trade's FROZEN beta
        broken = False
        if trade_is_open(pair, state):                                              # NOT BUILT (State)
            fail_count = state_fail_count(pair, state)                              # NOT BUILT (State)
            days_open = state_days_open(pair, state)                                # NOT BUILT (State)
            broken, fail_count = is_broken(spread, fail_count, days_open, rome["breakdown"],
                                           rome["formation"]["coint_trend"],
                                           rome["formation"]["coint_autolag"])
            state = set_fail_count(pair, state, fail_count)                         # NOT BUILT (State)

        # 5a. today's entry / exit / stop levels (config signal.threshold_mode: fixed | cost_aware)
        #     cost_over_sigma = round-trip cost / today's wiggle (the same N-day sigma the z-score used)
        N = rome["signal"]["zscore_lookback"]
        sigma_today = spread.iloc[-(N + 1):-1].std()
        cost = round_trip_cost(data[pair.a].iloc[-1], data[pair.b].iloc[-1],
                               rome["sizing"]["min_notional_per_leg"],         # swap for the real leg size once sizing.py exists
                               pair.half_life, rome["costs"])
        cost_over_sigma = cost / sigma_today
        entry_level, exit_level, stop_level = levels(rome["signal"], cost_over_sigma)

        # 5b. the decision: new direction (+1 long spread, -1 short spread, 0 flat) and why
        direction = state_direction(pair, state)                                    # NOT BUILT (State): 0 if flat
        days_held = state_days_open(pair, state)                                    # NOT BUILT (State): 0 if flat
        entry_half_life = state_entry_half_life(pair, state)                        # NOT BUILT (State)
        can_enter = pair.selected                                                   # exit-only pairs can't open
        new_direction, reason = next_action(z_today, direction, days_held, entry_half_life, broken, can_enter,
                                            entry_level, exit_level, stop_level,
                                            rome["signal"], rome["breakdown"])

        # 6. how many shares of each leg we WANT to hold after tomorrow's open (0 = flat)
        targets[pair.pair_id] = target_shares(pair, new_direction, spread, data, rome["sizing"])  # NOT BUILT

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
