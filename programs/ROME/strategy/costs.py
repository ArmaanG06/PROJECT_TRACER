BPS = 10_000          # 1 basis point = 1 / 10,000
TRADING_DAYS_PER_YEAR = 252


def _commission(shares: float, price: float, costs_cfg: dict):
    """per-share fee, but never less than the minimum and never more than the cap (% of trade value)."""
    fee = shares * costs_cfg["commission_per_share"]
    floor = costs_cfg["min_commission"]
    trade_value = shares * price    
    cap = trade_value * costs_cfg["max_commission_pct"]

    if fee < floor:
        fee = floor
    if fee > cap:
        fee = cap

    return fee


def fill_cost(shares: float, price: float, costs_cfg: dict):
    """Total cost of ONE fill (a single buy or a single sell of one leg), in dollars.
    commission + half the bid-ask spread + FX conversion
    """
    trade_value = shares * price
    fee = _commission(shares, price, costs_cfg)
    spread_cost = trade_value * costs_cfg["half_spread_bps"] / BPS
    fx_cost = trade_value * costs_cfg["fx_bps"] / BPS

    return fee + spread_cost + fx_cost


def borrow_cost(short_value: float, holding_days: float, costs_cfg: dict):
    """Fee for borrowing the short leg for holding_days trading days, in dollars."""
    yearly_fee = short_value * costs_cfg["borrow_fee_annual"]
    return yearly_fee * holding_days / TRADING_DAYS_PER_YEAR


def round_trip_cost(price_a: float, price_b: float, notional: float, holding_days: float, costs_cfg: dict):
    """Cost of opening AND closing one pair trade, both legs, as a FRACTION of notional.
    Example: 0.005 means the round trip costs 0.5% of one leg's dollar value.
    """
    total = 0.0

    # 4 fills: buy + sell of leg a, sell + buy of leg b
    for price in (price_a, price_b):
        shares = notional / price
        total += (2 * fill_cost(shares, price, costs_cfg))

    total += borrow_cost(notional, holding_days, costs_cfg)

    return total / notional