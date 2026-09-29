from utils.utils import load_config

MODES = {"backtest", "paper", "live"}


def run(mode):
    if mode not in MODES:
        raise ValueError(f"Invalid mode type: {mode} is not in MODES ({MODES})")

    configs = load_config()
    rome = configs["strategies"]["ROME"]
    run_id = hash_config(rome)

    prices = open_prices(configs, read_only=True)
    trade_log = open_trade_log(configs)
    broker = make_broker(mode, configs) # sim_broker | ibkr_broker(paper) | ibkr_broker(live)
    dates = make_calendar(mode, configs, prices, trade_log)
                                                      # backtest: trading days of the chosen split (holdout once)
                                                      # paper/live: [today], run after the close, then exit

    specs = None                                      # PairSpec list; formed on the first step, then carried
    for t in dates:
        specs = step(t, prices, broker, trade_log, specs, rome, run_id)

    build_report(run_id)


def step(t, prices, broker, trade_log, specs, rome, run_id):
    data = prices.upto(t)

    # 1. get the orders that filled this morning from yesterdays signals -> log them -> rebuild the state from confirmed fills
    fills = broker.get_fills(t)
    trade_log.write(fills, run_id)
    state = rebuild_from_log(trade_log)

    # 2. state vs broker holdings must agree (sim too, it costs nothing)
    if not reconcile(state, broker.get_portfolio()):
        halt_and_alert(t)

    # 3. formation: refit on refit days; live starts with no specs, so re-form as of the last refit day
    if is_refit_day(t) or specs is None:
        specs = form_pairs(data.window(last_refit_day(t), rome["formation"]["lookback_days"]), rome)
        state = mark_exit_only(state, specs)          # open pairs that dropped out -> exit-only

    # 4. engine -> TARGET positions + updated strategy memory (Kalman beta/alpha/P, breakdown counts)
    targets, state = engine(data, specs, state, rome)
    save_state(state)

    # 5. targets - holdings = orders (idempotent), filled at the next open
    orders = make_orders(targets, broker.get_portfolio())
    orders = broker.review(orders)                    # sim: pass-through | IBKR: stage for human approve/veto
                                                      # before the open; vetoes go to the trade log
    broker.execute(orders)

    return specs
