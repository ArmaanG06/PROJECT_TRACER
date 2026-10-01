import pandas as pd

from utils import get_project_root, hash_config, load_config

# ---- BUILT --------------------------------------------------------------
from ROME.strategy.formation import form_pairs          # uses strategy/costs.py for its cost hurdle
from ROME.strategy.engine import decide_targets         # skeleton: spread/zscore/signals/... are wired in there

# ---- NOT BUILT YET (names from CLAUDE.md's file table) -------------------
# from ROME.execution.trades import make_orders
# from ROME.execution.state_mgmt import rebuild_from_log, reconcile, save_state, mark_exit_only
# from ROME.execution.sim_broker / ibkr_broker import ...   (sim_broker charges fills with costs.fill_cost)
# from ROME.report import build_report

MODES = {"backtest", "paper", "live"}


def run(mode):
    if mode not in MODES:
        raise ValueError(f"Invalid mode type: {mode} is not in MODES ({MODES})")

    # ======================================================================
    # SETUP (once per run)
    # ======================================================================
    configs = load_config()
    rome = configs["strategies"]["ROME"]
    root = get_project_root()
    run_id = hash_config(rome)                        # variant ID = hash of strategies.ROME only
    db_file = root / rome["db"]

    # paper/live: add today's close to the db BEFORE loading prices (a backtest never touches the db)
    if mode != "backtest":
        pull_today_prices(db_file)                    # NOT BUILT (Live readiness item)

    prices = open_prices(db_file)                     # NOT BUILT: working version is
                                                      # research/formation_scan.load_prices -> move it here
    pairs = pd.read_csv(root / rome["formation"]["pairs_file"])
    trade_log = open_trade_log(configs)               # NOT BUILT

    broker = make_broker(mode, configs)               # NOT BUILT: sim_broker | ibkr_broker(paper) | ibkr_broker(live)
    dates = make_calendar(mode, configs, prices, trade_log)
                                                      # backtest: every trading day of the chosen split
                                                      # paper/live: just [today] -> the loop runs once, then exits

    # ======================================================================
    # THE DAILY LOOP (runs after each day's close)
    # ======================================================================
    specs = None                                      # this month's PairSpecs; replaced on each refit day

    for t in dates:
        data = prices.loc[:t]                         # look-ahead guard: nothing after day t is visible

        # ---- A. this morning: record the fills from yesterday's orders -------------------
        fills = broker.get_fills(t)                   # NOT BUILT
        trade_log.write(fills, run_id)
        state = rebuild_from_log(trade_log)           # NOT BUILT: state only changes on confirmed fills

        if not reconcile(state, broker.get_portfolio()):  # NOT BUILT: our records vs the broker's
            halt_and_alert(t)

        # ---- B. once a month: re-test the pairs (formation, BUILT) ----------------------
        if specs is None or is_refit_day(t):          # NOT BUILT: is_refit_day, last_refit_day
            specs = form_pairs(data, last_refit_day(t), pairs, rome)
            state = mark_exit_only(state, specs)      # NOT BUILT: open pairs that dropped out -> exit-only

        # ---- C. tonight: decide what we want to hold tomorrow ---------------------------
        targets, state = decide_targets(data, specs, state, rome)    # the engine (strategy/engine.py)
        save_state(state)                             # NOT BUILT: Kalman beta/alpha/P, breakdown counts

        # ---- D. send the orders that get us there (they fill at tomorrow's open) --------
        orders = make_orders(targets, broker.get_portfolio())   # NOT BUILT: targets - holdings
        orders = broker.review(orders)                # sim: pass-through | IBKR: I approve/veto before the open
        broker.execute(orders)

    build_report(run_id)                              # NOT BUILT
