import math


def leg_dollars(beta: float, sizing_cfg: dict):
    base = sizing_cfg["leg_notional"]

    if sizing_cfg["hedge_weighting"] == "dollar":
        return base, base

    if beta <= 0:
        raise ValueError(f"beta {beta} <= 0: beta-weighted sizing needs a positive beta")

    if beta >= 1:
        dollars_a = base
        dollars_b = beta * base
    else:
        dollars_a = base / beta
        dollars_b = base

    return dollars_a, dollars_b


def target_shares(direction: int, price_a: float, price_b: float, beta: float, sizing_cfg: dict):
    if direction == 0:
        return 0, 0

    dollars_a, dollars_b = leg_dollars(beta, sizing_cfg)
    shares_a = math.floor(dollars_a / price_a)
    shares_b = math.floor(dollars_b / price_b)

    # never trade one leg on its own
    if shares_a == 0 or shares_b == 0:
        return 0, 0

    if direction == 1:
        return shares_a, -shares_b
    return -shares_a, shares_b


def gross_budget(sizing_cfg: dict):
    capital_usd = sizing_cfg["capital"] * sizing_cfg["fx_cad_usd"]
    return capital_usd * sizing_cfg["max_gross_leverage"]


def entry_allowed(a: str, b: str, new_gross: float, open_trades: list, sizing_cfg: dict):
    # open_trades = [(a, b, gross), ...] for every open trade, incl. ones approved earlier today
    max_pairs = sizing_cfg["max_pairs"]
    if max_pairs is not None and len(open_trades) >= max_pairs:
        return False

    gross_used = 0.0
    trades_with_a = 0
    trades_with_b = 0
    for open_a, open_b, open_gross in open_trades:
        gross_used = gross_used + open_gross
        if a == open_a or a == open_b:
            trades_with_a = trades_with_a + 1
        if b == open_a or b == open_b:
            trades_with_b = trades_with_b + 1

    if gross_used + new_gross > gross_budget(sizing_cfg):
        return False

    per_ticker = sizing_cfg["max_pairs_per_ticker"]
    if trades_with_a >= per_ticker or trades_with_b >= per_ticker:
        return False

    return True
