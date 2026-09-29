# CLAUDE.md: Project Tracer / ROME

## How to work with me
- I write the code. You spec, review and stress-test. Don't write large blocks of code unless I ask.
- Push back hard. Don't agree by default. Kill bad ideas early and propose the better version.
- Be direct and concise. Lead with the answer. Assume quant fluency.
- Flag any unverified assumption explicitly.
- Never commit or push to git. I handle all git myself.
- Build agile: one file at a time. Spec → I code → you review → next file.
- When I ask for next steps, use the same format every time: bold numbered step titles, each with
  one or two plain-English lines underneath. Concise, in build order, done items left out.
- **Keep this file current.** When a decision is made, a file is finished, or a TBD is resolved,
  update the relevant section and tell me what you changed.

## Project
- Project Tracer = my personal trading book. Algos are named after world cities.
- ROME = first algo: ETF pairs trading. Long the cheap leg, short the rich leg on a stretched spread,
  close on reversion.
- Capital: C$10k total, ~C$4k deployable until a successful backtest. IBKR non-registered, CAD.
  Minimum $1,000 notional per leg.

## Repo layout
- `data/data_pulling/`: data layer (DONE). `from data_pulling import get_prices`.
  Sources: IBKR (primary), WRDS/CRSP, yfinance, with automatic failover. Data is stored in
  ROME.duckdb. Backtests read frozen snapshots.
- `programs/ROME/strategy/` and `programs/ROME/execution/`: being built now.
- `configs.yaml` (central, read by `utils.utils.load_config`) has one section per program.
  ROME settings live under `strategies.ROME`. Each run logs a hash of that section only (the variant ID).
- Run controls (`mode`, `split`, `holdout_unlocked`) live in the top-level `run:` block, outside
  the hash, so a backtest and a paper run of the same variant share one ID.

## Architecture
configs.yaml + ROME.duckdb + ROME_pairs.csv → runner.py
runner → formation.py (monthly) → engine.py (daily) ↔ state_mgmt.py
engine → target positions → trades.py (targets − holdings = orders)
trades → sim_broker.py (+ portfolio.py) OR ibkr_broker.py
both brokers → ROME_tradelog.duckdb → report.py, and → state_mgmt.rebuild_from_log()

Principles:
- One engine for backtest and live. The broker is the only mode switch.
- Walk-forward is built in: formation is called inside the runner loop. No separate backtest harness.
- The engine outputs TARGET POSITIONS, not buy/sell signals. trades.py diffs against holdings, so
  it's idempotent (sending the same targets twice places zero orders).
- Holdings come from the broker: portfolio.get_portfolio() (sim) or ibkr_broker.get_portfolio() (live).
- state_mgmt = strategy memory ONLY: pair ID, direction, frozen entry β, entry date, entry
  half-life, Kalman β/α/P, breakdown fail count, exit-only status. No share counts.
- State only moves to "open" when fills are confirmed. State is rebuilt from the trade log.
- Live: reconcile(state vs IBKR positions) before each day. On a mismatch, halt and alert.
- Live runs once per day after the close (scheduler), then exits. Not a forever loop.
- Every stage sees data ≤ t only. The runner enforces this.
- Daily order in runner.step(t): fills from today's open → log → rebuild state → reconcile
  (sim too) → refit if refit day → engine (targets + strategy memory) → orders for the next open.
- Mode is used in exactly two places: make_broker (how orders fill) and make_calendar (which dates run).
- Human gate (paper/live): orders are staged after the close, and I approve or veto them before the
  open. Vetoes are logged. The backtest assumes every order is approved; the veto log measures that gap.
- Formation specs are NOT persisted. Live re-forms as of the last refit day each run (deterministic).

## Files and key functions
| File | Functions | Notes |
|---|---|---|
| runner.py | run(mode), step(t), make_calendar, is_refit_day(t), last_refit_day(t), hash_config | Modes: backtest, paper, live |
| engine.py | engine(data, specs, state) → targets, state | Daily. Calls spread/zscore/signals/breakdown/sizing |
| (data wrapper, TBD home) | open_prices, .upto(t), .window() | Thin view over data_pulling. Enforces ≤ t |
| strategy/formation.py | form_pairs(prices, t, pairs, cfg) → PairSpec list (BUILT) | Returns ALL pairs with status + reason; top_n marked `selected`. Cost hurdle is a placeholder until costs.py |
| strategy/stats.py | hedge_ratio, cointegration, half_life (BUILT) | Pure functions on log-price Series. Uses statsmodels. rolling_adf not built yet (comes with breakdown.py) |
| kalman.py | kalman_init, kalman_update | β_t, α_t, P. Used for NEW entries only |
| spread.py | calc_spread(a, b, β, α) | Log prices |
| zscore.py | zscore(spread, lookback) | Rolling μ, σ. ⚠ Solve the drift-lag bias here (see Open/TBD) |
| signals.py | next_action(z, position, days_held, hl) | Enter, take-profit, stop, time stop, hold |
| breakdown.py | is_broken(pair, k) | k consecutive rolling-ADF fails |
| sizing.py | target_shares(pair, σ_spread, capital) | Dollar-neutral, sized off spread vol |
| costs.py | trade_cost, cost_hurdle | Used by sim fills and the formation filter |
| state_mgmt.py | open_trade_log, load_state, save_state, rebuild_from_log, reconcile, mark_exit_only | |
| trades.py | make_orders(targets, holdings) | |
| portfolio.py | get_portfolio, apply_fill | Sim only |
| sim_broker.py | get_fills, review, execute | Next-open fills. review = pass-through |
| ibkr_broker.py | get_fills, get_portfolio, review, execute | Market-on-open orders, paper account first. review = stage for human |
| report.py | build_report(run_id) | Reads the trade log only |
| (alerts, TBD home) | halt_and_alert | Email/push. Not built yet |

### Code structure (proposed, not decided)
- Hybrid. Classes only where there is state plus swappable implementations: Broker interface
  (SimBroker, IBKRBroker), PairSpec and State as dataclasses, the price view object.
- Pure functions for all the math (stats, spread, zscore, signals, breakdown, sizing, costs, trades)
  so the look-ahead and idempotency tests stay trivial. No single "classes" file.
- Folders: `strategy/` = formation, stats, kalman, spread, zscore, signals, breakdown, sizing, engine, costs.
  `execution/` = trades, portfolio, sim_broker, ibkr_broker, state_mgmt. runner.py and report.py at ROME root.

## Locked strategy decisions
- Pairs are chosen by hand on economic logic, then confirmed statistically. Never brute-force.
  ROME_pairs.csv has a rationale column. Lock the list and its count before looking at stats.
- Spreads are built on LOG total-return-adjusted prices. Mixing data sources is ALLOWED: the two legs
  of a pair (and symbols across the dataset) may come from different providers.
  (A single symbol's series is still never spliced across vendors; the data layer enforces that.)
- Cointegration: Engle-Granger on OLS residuals, trend="ct", MacKinnon critical values.
  NEVER test on Kalman residuals (they absorb the non-stationarity).
- Trending spreads are allowed and WILL be traded: a spread that drifts steadily and oscillates
  around that drift is trend-stationary, which is what the trend="ct" test checks for. A spread
  that wanders with no anchor (a random walk) is still rejected. Estimate half-life on the DETRENDED residual.
  Remove drift once only: rolling mean in OLS mode, α_t in Kalman mode.
- Engle-Granger direction: a on b only (symbol_a is the dependent leg, CSV order).
- Formation windows in months (config): lookback_months = 12 for β/α/half-life/σ,
  test_window_months = 12 for the cointegration test (may lengthen later).
- Negative β rejected (config `allow_negative_beta: false`): long both / short both is not a hedge.
- A leg needs ≥ 95% of the window's trading days (config `min_coverage`), else status no_data.
- top_n ranking: shortest half-life, p-value breaks ties (config `rank_by: half_life | pvalue`).
- Half-life filter: 1–30 days.
  Cost hurdle: entry_z × σ_spread > 3× round-trip cost across both legs.
- Signal: entry ±2, exit 0, stop ±3.5, time stop 3× half-life.
- Open trades keep their FROZEN entry β. Exit, stop and time-stop checks use the entry-β spread.
- A pair that drops out at refit becomes exit-only: hold to take-profit, stop or time stop.
- Confirmed breakdown (k consecutive fails): config toggle force_close | hold. Compare both.
- Fills at the NEXT OPEN, at the actual open price, gaps included (a 3.5 stop can fill at 4.5).
- Costs: commission, half-spread per leg, borrow fee, FX. Short-leg dividends are already in the
  total-return series. Do NOT charge them again.
- Sizing: dollar-neutral per pair, risk based on spread vol (not price vol).
- Capital in config = C$10,000. max_pairs is derived: capital // (2 × min_notional_per_leg).
  top_n is a fixed config value.

## Research hygiene
- Splits: train 2012–2019, validate 2020–2022, holdout 2023–now (run ONCE). Load data from 2010.
- Rolling formation window of 12 months (config lookback_months), refit monthly. Each formation sees only the
  last X months before its date (June 2015 formation = roughly June 2014 to end of May 2015).
  Test power is set by X alone: rolling repeats the test on overlapping windows, it doesn't add data.
- Write a hypothesis before any backtest. Log every variant (config hash, pair count).
- Parameters must hold up at neighbouring values.
- A realistic prior: net Sharpe of 0.5–1.0 is a good result.
- Compare OLS vs Kalman only after the OLS baseline is working.
- Test power (simulated, 252 days, trend="ct", p < 0.05; 300 runs each):
  true half-life 5d → caught 89%; 10d → 40%; 20d → 13%; not cointegrated → 6% false pass.
  The 1–30 day half-life filter does NOT screen out fake pairs (91% of random walks pass it).
  So with many candidate pairs, a large share of the passing pairs can be noise.
- First formation run (PRELIMINARY: only the 21 pairs with 2010+ data, all yfinance, 2012–19, 96 refits):
  15% of pair-months tradable (vs ~6% expected by chance), 3.1 tradable pairs per month on average
  (0 to 9). Most often tradable: HYG-JNK 44%, JNK-LQD 35%, HYG-LQD 34%. The half-life filter never
  rejected anything. Ranking by half-life vs p-value made no difference (top_n = 5 rarely binds
  when only ~3 pairs pass): median out-of-sample half-life 7 days either way.

## Open / TBD (resolve on TRAIN data only, before validation)
- z-score lookback + DRIFT-LAG BIAS (must be solved when zscore.py is built):
  - Problem: on a drifting spread the rolling mean sits N/2 days in the past, so it lags the drift
    line by about drift × N / 2. z then reads off-centre even when there is no mispricing.
  - Example: drift 0.0002/day, N = 60, spread vol 0.02 → lag 0.006 → z permanently +0.3.
    Entries fire at a true 1.7 on the drift side and need a true 2.3 on the other; exits at 0 are off too.
  - Options: (a) shorter lookback (less lag, noisier z); (b) measure z from the drift line fitted at
    formation instead of the rolling mean (still removes drift once only); (c) either way, check on
    train that each pair's average z is ≈ 0.
- Kalman δ and observation variance
- Breakdown window, p-value and k
- ⚠ DATA BLOCKER for the kill/continue run: ROME.duckdb only has 2010+ history for the 16 yfinance
  symbols. The 26 WRDS symbols cover 2022–23 only (GLD/GDX from 2020, SLV from 2021). Re-pull those
  26 for 2010–now (any source) before running formation over 2012–19.
- DEFERRED (config `multiple_testing: none` for now): how to handle the ~4 fake passes per refit
  (72 pairs × ~6%). Read the kill/continue pass counts with this in mind. Options:
  - Longer window for the cointegration TEST only (β still from 252d). Simulated, trend="ct":
    252d catches HL10 38% / HL20 17%; 504d catches HL10 90% / HL20 42%. Fake rate ~6–8% either way.
  - Persistence: pass in k of the last m formations. Weaker than it looks: monthly windows share
    ~90% of their data, so fake passes persist too.
  - Multiple-testing correction across the 72 (e.g. Benjamini-Hochberg).
  - trend="c" is NOT an option: on drifting spreads it misses most real pairs (18% at HL10).

## Live readiness (spec only, DO NOT BUILD until the paper-trading stage)
The runner alone doesn't trade: with every helper built and live mode on, it stages one day of
orders and exits. These are needed before paper/live. Rules marked TBD are decided later.
- Daily data refresh: pull today's close into ROME.duckdb before step() runs. Backtests keep
  reading frozen snapshots.
- Scheduler: an OS scheduler (e.g. Windows Task Scheduler) launches run("live") after each close.
  Kept outside the runner.
- Approval command: separate command that shows the staged orders, records approve/veto, and
  submits the approved ones as market-on-open orders before the cutoff. Unapproved orders expire, never carry over.
  - TBD: veto semantics. Targets are recomputed daily, so a vetoed entry comes back tomorrow if z is
    still stretched. "Not today" vs "skip until the signal resets".
  - TBD (unverified): the exact MOO cutoff for each exchange the pairs trade on.
- IBKR session: TWS/Gateway must be running and logged in. IBKR forces periodic re-logins, which
  will break unattended runs. Needs a check at the start of each run.
- One-legged fills and borrow: check the short leg is shortable before submitting either leg.
  TBD: what to do if only one leg fills (reconcile will halt, but there's no rule to fix it).
- Adjusted vs raw prices: signals use total-return-adjusted prices; share counts must use RAW prices.
  Sizing needs both.
- Currency: the account is in CAD. If any leg is a US ETF, sizing and costs need an FX conversion. TBD.
- Kill switch: TBD drawdown / daily-loss limit that halts new entries. Must exist before real money.

## Build order / status
- [x] Data layer
- [ ] runner.py (pseudocode draft 2 approved; real code gets filled in as the modules it calls are built)
- [x] Pair list: LOCKED at 72 pairs (data/store/universes/ROME_pairs.csv). Final, no cuts.
- [x] stats.py (hedge_ratio, cointegration, half_life; checked on simulated data)
- [x] formation.py (tested: synthetic cases + look-ahead pass; preliminary real run on 21 pairs)
- [ ] Re-pull the 26 short-history symbols for 2010–now, any source (data blocker)
- [ ] Full formation run on 2012–19, all 72 pairs (kill/continue gate)
- [ ] spread / zscore (solve drift-lag bias first) → signals → breakdown → sizing → engine (look-ahead test)
- [ ] costs + portfolio + sim_broker → trades → full backtest → report
- [ ] kalman → compare OLS vs Kalman
- [ ] state_mgmt + ibkr_broker + everything under "Live readiness" → paper trading + parity test
- [ ] holdout (once) → live at 1/3 size

## Required tests
- Look-ahead: output at t is identical whether computed on data truncated at t or on the full data.
- Idempotency: the same targets sent twice produce zero orders.
- Frozen β: an open trade's exit uses its entry β.
- Gap fill: fills happen at the open, not at the stop level.
- Parity: replaying N paper-trading days through the backtest gives identical targets.