from datetime import datetime
import pandas as pd
import duckdb

from utils.utils import load_config

configs = load_config()
MODES = {"sim", "live"}
db = duckdb.connect(configs["data"]["DB_path"] + "/ROME.duckdb")
trade_log = duckdb.connect(configs["data"]["trade_log"] + "/ROME_trade_log.duckdb")


def run(mode):
    if mode not in MODES:
        raise ValueError(f"Invalid mode type: {mode} is not in MODES ({MODES})")

    training_dates = configs["strategies"]["ROME"]["splits"]["train"]
    validate_dates = configs["strategies"]["ROME"]["splits"]["validate"]
    holdout_dates = configs["strategies"]["ROME"]["splits"]["holdout"]

    training_start, training_end = training_dates["start"], training_dates["end"]
    validate_start, validate_end = validate_dates["start"], validate_dates["end"]
    holdout_start, holdout_end = holdout_dates["start"], holdout_dates["end"]

    training_month_list = pd.date_range(start=training_start, end=training_end, freq='M')
    validate_month_list = pd.date_range(start=validate_start, end=validate_end, freq='M')
    holdout_month_list = pd.date_range(start=holdout_start, end=holdout_end, freq='M')

    for month in training_month_list:
        formation(db, month, mode, configs)
        for day in pd.date_range(start=month, end=month + pd.offsets.MonthEnd(0), freq='B'):
            state = get_state(db, day, configs)
            signals = engine(db, day, mode, configs, state)
            trades = trades(signals, configs)
            if mode == "sim":
                sim_broker(trades)
            if mode == "live":
                live_IBKR(trades)

            trade_log.update(trades,day)
            update_state(db, day, trades, configs)
            generate_report(db, day, trades, configs)

    if configs["split_control_panel"]["validate"] == True:
        pass #not sure what to do here yet

    if configs["split_control_panel"]["holdout"] == True:
        pass #not sure what to do here yet
        

            

    