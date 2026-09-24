# ROME — ETF pairs trading

- ROME = ETF pairs trading. Long the cheap leg, short the rich leg, exit on reversion.
- Architecture: formation (monthly) → `engine.step` (daily) → target positions → broker.
- One engine for backtest AND live. **The broker is the only mode switch.**
- Walk-forward = the formation call inside the runner loop. No separate harness.
- Data comes in one way only: `from data_pulling import get_prices`.
- Config lives in the root `configs.yaml` under `strategies.ROME`.

## Build order

1. `pairs` → `formation` → `spread`/`zscore`
2. `state_machine` → `sizing` → `engine`
3. `sim_broker` + `costs` → `runner` → `report`
4. `kalman` → compare OLS vs Kalman
5. `ibkr_broker` (paper)

## Layout

```
strategy/    pairs, formation, kalman, spread, zscore, state_machine, sizing, engine
execution/   broker_base, sim_broker, ibkr_broker, runner, state_store, costs, report
tests/       test_plan.md
```

Every file currently holds a plain-English spec only — no implementation yet.
