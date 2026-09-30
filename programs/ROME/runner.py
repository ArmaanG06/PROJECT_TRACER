import pandas as pd

from utils.utils import get_project_root, load_config

# ---- BUILT --------------------------------------------------------------
from ROME.strategy.formation import form_pairs
from ROME.strategy.spread import pair_spread            # skeleton, being coded now

# ---- NOT BUILT YET (names from CLAUDE.md's file table) -------------------
# from ROME.strategy.zscore import zscore
# from ROME.strategy.signals import next_action
# from ROME.strategy.breakdown import is_broken
# from ROME.strategy.sizing import target_shares
# from ROME.execution.trades import make_orders
# from ROME.execution.state_mgmt import rebuild_from_log, reconcile, save_state, mark_exit_only
# from ROME.execution.sim_broker / ibkr_broker import ...
# from ROME.report import build_report

MODES = {"backtest", "paper", "live"}


def run(mode):
    if mode not in MODES:
        raise ValueError(f"Invalid mode type: {mode} is not in MODES ({MODES})")

    configs = load_config()
    rome = configs["strategies"]["ROME"]
    root = get_project_root()
    run_id = hash_config(rome)                        # NOT BUILT: hash of strategies.ROME only

    # inputs (all paths come from configs.yaml)
    prices = open_prices(root / rome["db"])           # NOT BUILT: working version is
                                                      # research/formation_scan.load_prices -> move it here
    pairs = pd.read_csv(root / rome["formation"]["pairs_file"])
    trade_log = open_trade_log(configs)               # NOT BUILT

    # mode is used on these two lines only; everything below is identical in every mode
    broker = make_broker(mode, configs)               # NOT BUILT: sim_broker | ibkr_broker(paper) | ibkr_broker(live)
    dates = make_calendar(mode, configs, prices, trade_log)
                                                      # backtest: trading days of the chosen split (holdout once)
                                                      # paper/live: [today], run after the close, then exit

    specs = None                                      # PairSpec list; formed on the first step, then carried
    for t in dates:
        specs = step(t, prices, pairs, broker, trade_log, specs, rome, run_id)

    build_report(run_id)                              # NOT BUILT


def step(t, prices, pairs, broker, trade_log, specs, rome, run_id):
    data = prices.loc[:t]                             # look-ahead guard: nothing after t goes past here

    # 1. yesterday's orders filled at today's open -> log -> state rebuilt from confirmed fills
    fills = broker.get_fills(t)                       # NOT BUILT
    trade_log.write(fills, run_id)
    state = rebuild_from_log(trade_log)

    # 2. state vs broker holdings must agree (sim too, it costs nothing)
    if not reconcile(state, broker.get_portfolio()):  # NOT BUILT
        halt_and_alert(t)

    # 3. formation (BUILT): refit on refit days; live starts with no specs, so re-form as of the last refit day
    if is_refit_day(t) or specs is None:
        refit_date = last_refit_day(t)                # NOT BUILT (runner helper)
        specs = form_pairs(data, refit_date, pairs, rome["formation"])
        state = mark_exit_only(state, specs)          # NOT BUILT: open pairs that dropped out -> exit-only

    # 4. the daily strategy, one module at a time. The runner is the ONLY place they are wired
    #    together: no strategy file imports another pipeline stage.
    targets = {}
    for pair in pairs_to_manage(specs, state):        # NOT BUILT: selected pairs + open trades
        # open trade -> FROZEN entry beta/alpha from state; new entry -> today's formation beta/alpha
        beta, alpha = hedge_for(pair, state)          # NOT BUILT

        spread = pair_spread(data, pair.a, pair.b, beta, alpha)                    # BUILT (skeleton)
        z = zscore(spread, rome["signal"]["zscore_lookback"])                     # NOT BUILT
        broken = is_broken(pair, state, rome["breakdown"])                        # NOT BUILT
        action = next_action(z, pair, state, broken, rome["signal"])              # NOT BUILT
        targets[pair.pair_id] = target_shares(pair, action, spread, rome["sizing"])  # NOT BUILT

    save_state(state)                                 # NOT BUILT: Kalman beta/alpha/P, breakdown counts

    # 5. targets - holdings = orders (idempotent), filled at the next open
    orders = make_orders(targets, broker.get_portfolio())   # NOT BUILT
    orders = broker.review(orders)                    # sim: pass-through | IBKR: stage for human approve/veto
                                                      # before the open; vetoes go to the trade log
    broker.execute(orders)

    return specs
