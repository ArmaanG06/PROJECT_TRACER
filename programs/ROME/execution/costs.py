"""Every cost that stands between the signal and the P&L.

- IBKR tiered commission, per leg, with the per-order minimum.
- Half the bid-ask spread per leg, charged on entry and on exit.
- Short borrow fee on the short leg, accrued daily while held.
- CAD<->USD FX conversion where the account currency differs from the ETF's.
- Total-return data ALREADY includes the short leg's dividends via adj_close.
  Do NOT charge them again — that is double counting.
- Formation's cost filter and this module must use the SAME numbers, or pairs
  get approved on costs they never actually pay.
- Output: cost per fill plus a daily carry figure, both logged for cost drag.
"""
