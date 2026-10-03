# CLAUDE.md: Project Tracer / ROME

## How to work with me
- I write the code. You spec, review and stress-test. Don't write large blocks of code unless I ask.
- Push back hard. Don't agree by default. Kill bad ideas early and propose the better version.
- Be direct and concise. Lead with the answer. Assume quant fluency.
- Flag any unverified assumption explicitly.
- Write code I can read line by line: one idea per line, plain loops, step comments. No dense
  chained pandas one-liners. Don't run code when I say not to.
- Never commit or push to git. I handle all git myself.
- Build agile: one file at a time. Spec → I code → you review → next file.
- When I ask for next steps, use the same format every time: bold numbered step titles, each with
  one or two plain-English lines underneath. Concise, in build order, done items left out.
  Always the WHOLE remaining roadmap through to live, grouped by phase, not just the current phase.
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
- `configs.yaml` (central, read by `utils.load_config`; utils.py sits at the repo root, also holds hash_config) has one section per program.
  ROME settings live under `strategies.ROME`. Each run logs a hash of that section only (the variant ID).
- Run controls (`mode`, `split`, `holdout_unlocked`) live in the top-level `run:` block, outside
  the hash, so a backtest and a paper run of the same variant share one ID.

## Architecture
configs.yaml + ROME.duckdb + ROME_pairs.csv → runner.py
runner → formation.py (monthly) ↔ state_mgmt.py
runner daily loop → engine.decide_targets: hedge (OLS/Kalman) → spread → zscore → breakdown → signals → sizing → target positions
runner → trades.py (targets − holdings = orders)
trades → sim_broker.py (+ portfolio.py) OR ibkr_broker.py
both brokers → ROME_tradelog.duckdb → report.py, and → state_mgmt.rebuild_from_log()

Principles:
- ONLY runner.py and strategy/engine.py wire pipeline stages together. The runner runs the day
  (fills, formation, orders) and calls engine.decide_targets() once a day; the engine calls the
  daily stages (kalman, spread, zscore, breakdown, signals, sizing). No stage file imports another
  stage. Exceptions: models.py (data classes) and toolboxes like stats.py may be imported anywhere.
- configs.yaml is the control centre: every tunable number, path and switch comes from it. No
  hard-coded parameters in code (only defaults on pure functions, overridden by config at the call).
- One code path for backtest and live. Mode only matters in run() setup (see below), never in the daily loop.
- Walk-forward is built in: formation is called inside the runner loop. No separate backtest harness.
- decide_targets outputs TARGET POSITIONS, not buy/sell signals. trades.py diffs against holdings, so
  it's idempotent (sending the same targets twice places zero orders).
- Holdings come from the broker: portfolio.get_portfolio() (sim) or ibkr_broker.get_portfolio() (live).
- state_mgmt = strategy memory ONLY: pair ID, direction, frozen entry β, entry date, entry
  half-life, Kalman β/α/P, breakdown fail count, exit-only status. No share counts.
- State only moves to "open" when fills are confirmed. State is rebuilt from the trade log.
- Live: reconcile(state vs IBKR positions) before each day. On a mismatch, halt and alert.
- Live runs once per day after the close (scheduler), then exits. Not a forever loop.
- Every stage sees data ≤ t only. The runner enforces this.
- Daily loop in runner.run (no step function; loop body is inline, blocks A–D):
  A. fills from today's open → log → rebuild state → reconcile (sim too)
  B. refit if refit day (formation) → mark exit-only
  C. engine.decide_targets (per pair: hedge → spread → zscore → breakdown → signals → sizing)
     → targets + updated strategy memory → save state
  D. targets − holdings = orders → human review (paper/live) → execute at the next open.
- Mode is used in exactly three places, all in run() setup: make_broker (how orders fill), make_calendar
  (which dates run) and pull_today_prices (paper/live only). The daily loop never checks mode.
- Human gate (paper/live): orders are staged after the close, and I approve or veto them before the
  open. Vetoes are logged. The backtest assumes every order is approved; the veto log measures that gap.
- Formation specs are NOT persisted. Live re-forms as of the last refit day each run (deterministic).

## Files and key functions
| File | Functions | Notes |
|---|---|---|
| runner.py | run(mode), make_calendar, is_refit_day(t), last_refit_day(t) | Modes: backtest, paper, live. Imports formation + engine; the rest are commented stubs |
| strategy/engine.py | decide_targets(data, specs, state, rome) → targets, state; pairs_to_manage; hedge_for (SKELETON) | Daily per-pair chain. Pseudocode until the stages it calls exist |
| (data wrapper, TBD home) | open_prices | Working version exists: research/formation_scan.load_prices → move it here |
| research/formation_scan.py | load_prices, refit_dates, scan, summarise (BUILT) | Kill/continue scan. Split + output dir from config `research:` |
| models.py | HedgeFit, CointResult, PairSpec (State to come) | ALL data-only classes live here. Any file may import it without importing another stage |
| strategy/formation.py | form_pairs(prices, t, pairs, rome) → PairSpec list (BUILT) | Takes the whole strategies.ROME section. Lookback applied in _window(t, months from config). Returns ALL pairs with status + reason; top_n marked `selected`. Cost hurdle LIVE (costs.py), sized at min_notional_per_leg, judged on the typical N-day σ (same σ as the z-score). Skipped entirely when costs.enabled is false. PairSpec.sigma is still the 12-month detrended σ (descriptive only) |
| strategy/stats.py | hedge_ratio, cointegration, half_life, adf_pvalue (BUILT) | Pure functions. Uses statsmodels. adf_pvalue = plain ADF on one series with a FIXED beta (breakdown); cointegration = Engle-Granger, estimates beta (formation) |
| strategy/kalman.py | kalman_init, kalman_update | β_t, α_t, P. Used for NEW entries only (hedge.method: kalman) |
| strategy/spread.py | pair_spread(prices, a, b, β, α) (BUILT) | spread = log(adj_a) − α − β·log(adj_b), on dates where both legs have a price. No trend term (drift removed in zscore). engine.hedge_for passes frozen β/α for open trades. Checked: matches formation's residual + trend line to 1e-15 |
| strategy/zscore.py | zscore(spread, N) → Series of z (BUILT) | Option A: (spread − mean of previous N days) / std of previous N days. N = config signal.zscore_lookback. std 0 → NaN. Checked: hand check, no cap, look-ahead, flat cases |
| strategy/breakdown.py | is_broken(spread, fail_count, days_open, breakdown_cfg, trend, autolag) → broken, fail_count (BUILT) | Open trades only, frozen-β spread. Tests every check_every_days; p ≥ pvalue = fail; pass resets the count; not a check day / short history = no change. Only REPORTS; signals decides force_close/hold. Engine reads/writes fail_count + days_open in state (State not built yet) |
| strategy/signals.py | levels(signal_cfg, cost_over_sigma) → entry, exit, stop; next_action(z_today, direction, days_held, entry_half_life, broken, can_enter, entry/exit/stop levels, signal_cfg, breakdown_cfg) → new_direction, reason (BUILT) | Direction +1 long spread / −1 short / 0 flat. Open: broken(force_close) → time stop → no z = hold → stop → profit → hold. Flat: exit-only → no z → too stretched (≥ stop) → enter → flat. cost_aware: entry = max(entry_z, mult × cost/σ), stop keeps its gap above entry. 19/19 test cases pass. Reason strings go to the trade log |
| strategy/sizing.py | target_shares(pair, action, spread, data, sizing_cfg) | Dollar-neutral, sized off spread vol. Share counts from RAW prices |
| strategy/costs.py | _commission (private), fill_cost, borrow_cost, round_trip_cost(price_a, price_b, notional, holding_days, costs_cfg) → fraction of notional (BUILT) | Toolbox like stats.py: formation's cost hurdle uses round_trip_cost (now LIVE); sim_broker will use fill_cost + borrow_cost. Settings in config `costs:` (estimates, verify vs IBKR). `costs.enabled: false` → fill_cost and borrow_cost return 0, so every cost (charges AND the cost-based filters) turns off together |
| execution/state_mgmt.py | open_trade_log, load_state, save_state, rebuild_from_log, reconcile, mark_exit_only | State dataclass goes in models.py |
| execution/trades.py | make_orders(targets, holdings) | |
| execution/portfolio.py | get_portfolio, apply_fill | Sim only |
| execution/sim_broker.py | get_fills, review, execute | Next-open fills, charged with costs.fill_cost / borrow_cost. review = pass-through |
| execution/ibkr_broker.py | get_fills, get_portfolio, review, execute | Market-on-open orders, paper account first. review = stage for human |
| report.py | build_report(run_id) | Reads the trade log only. Always shows profit BEFORE and AFTER costs side by side (trade log records each fill's cost) |
| (alerts, TBD home) | halt_and_alert | Email/push. Not built yet |

### Code structure (decided)
- Hybrid. Data-only classes (PairSpec, HedgeFit, CointResult, later State) ALL live in models.py.
  Classes with behaviour (Broker interface: SimBroker, IBKRBroker) stay in their own files.
- Pure functions for all the math (stats, spread, zscore, signals, breakdown, sizing, costs, trades)
  so the look-ahead and idempotency tests stay trivial.
- Folders: `strategy/` = engine, formation, stats, costs, kalman, spread, zscore, signals, breakdown, sizing.
  `execution/` = trades, portfolio, sim_broker, ibkr_broker, state_mgmt.
  ROME root = runner.py, models.py, report.py. `research/` = one-off analysis scripts (formation_scan).
  Repo root = utils.py (load_config, get_project_root, hash_config), configs.yaml.

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
  Remove drift once only: rolling mean in OLS mode, α_t in Kalman mode. (Formation's fitted trend is
  used for the test and half-life only, never projected forward for trading.)
- Engle-Granger direction: a on b only (symbol_a is the dependent leg, CSV order).
- Formation windows in months (config): lookback_months = 12 for β/α/half-life/σ,
  test_window_months = 12 for the cointegration test (may lengthen later).
- Negative β rejected for now (config `allow_negative_beta: false`). Correction to the original
  reasoning: an inverse pair IS risk-hedged (the legs move opposite, so long both offsets). The real
  problems are that it is not dollar-neutral (long both = 2× cash; short both = borrow on both legs)
  and signals/sizing are being built for one long + one short leg. The toggle only affects
  formation today; flipping it requires sizing, signals and trades to handle same-side legs.
- A leg needs ≥ 95% of the window's trading days (config `min_coverage`), else status no_data.
- top_n ranking: shortest half-life, p-value breaks ties (config `rank_by: half_life | pvalue`).
- Half-life filter: 1–30 days.
  Cost hurdle: entry_z × typical σ > 3× (config cost_hurdle_mult) round-trip cost across both legs,
  with each leg sized at sizing.min_notional_per_leg and holding time = the half-life.
  typical σ = median of the rolling N-day std (N = signal.zscore_lookback) of the spread over the
  formation year: the SAME σ the z-score trades on. NOT the 12-month σ (≈2× bigger, overstated every trade).
  With costs.enabled false the hurdle is skipped (every pair passes it).
- Z-SCORE = OPTION A (decided on train data, see Research hygiene): plain rolling z of the spread,
  z = (spread today − mean of the N days BEFORE today) / std of those N days. Formation's drift line
  is NOT used for z (it doesn't persist out of sample). Drift is handled by the rolling mean only.
  "Days before today" (not including today) because including today caps |z| at (N−1)/√N
  (N=10 → 2.85, so a 3.5 stop could never fire).
- Signal thresholds in z units, ONE set for all pairs: entry ±2, exit 0, stop ±3.5, time stop 3× half-life.
  Config signal.threshold_mode: fixed (baseline) | cost_aware (entry rises when cost/σ is high; stop
  keeps its 1.5 gap). Compare both in the backtest. Market-regime levels NOT built (preview showed no
  regime effect in z units). No-fresh-z day: open trade HOLDS (time stop / broken still fire); flat
  pair stays flat. Already past the stop when flat → don't enter. Time stop uses the half-life frozen at entry.
- Later, only if the backtest shows repeat stop-outs: a re-entry cool-down after a stop.
  Starting values, tuned in the backtest. No per-pair thresholds: the rolling z already adapts to each
  pair and to the volatility regime (see Research hygiene).
- Open trades keep their FROZEN entry β. Exit, stop and time-stop checks use the entry-β spread.
- A pair that drops out at refit becomes exit-only: hold to take-profit, stop or time stop.
- Confirmed breakdown (k consecutive fails): config toggle force_close | hold. Compare both.
  Settings (from simulation, 30-day trades): window 252, fail if p ≥ 0.30, weekly checks, k = 3.
  Old 126 / 0.10 / daily flagged 55–82% of HEALTHY pairs broken. New: 0–7% false alarms, catches 72%
  of truly broken pairs. Breakdown is a SLOW backstop; the stop (±3.5) and time stop are the fast protection.
- Fills at the NEXT OPEN, at the actual open price, gaps included (a 3.5 stop can fill at 4.5).
- Costs toggle (config costs.enabled): OFF = the strategy on merit (free trading, no cost filters).
  Diagnostic only; every real decision and the backtest gate are judged with costs ON.
  Two different questions: the toggle = "what would the strategy CHOOSE with free trading?";
  the report's before/after-cost columns = "how much did costs drag on the trades actually taken?".
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
- KILL/CONTINUE RESULT (full run, all 72 pairs, 2012–19, 96 refits, research/output/formation_scan_train.csv):
  CONTINUE.
  - 12.1% of pair-months tradable vs ~6% by chance → real signal, but up to about half of the
    passing pairs in a month could be chance passes (~4 of 8.7).
  - 8.7 tradable pairs per month on average (3 to 20), never zero. By year: 9.1, 8.8, 8.7, 8.3,
    7.9, 12.7 (2017), 5.4 (2018), 9.0. top_n = 5 filled nearly every month (4.9 average).
  - Top pass rates: HYG-JNK 44%, JNK-LQD 35%, HYG-LQD 34%, SLV-SIL 27%, SLV-GDX 26%, XLV-XLP 22%.
  - Only FXB-UUP and FXE-UUP never pass (negative β every month). No no_data after the re-pull.
  - Negative β filter removes 9.5% of pair-months, but only ~0.6 per month would pass everything else.
  - Tradable half-lives are fast: median 5.4 days (10th–90th pct 3.8–8.4). Half-life filter never binds.
  - Persistence: a tradable pair is tradable again next month only 58% of the time → expect
    exit-only churn.
- COST HURDLE IMPACT (re-checked on the train scan's tradable rows, $1,000 legs, config cost estimates):
  - Round trip ≈ 0.49% of notional; ~$4 of the ~$4.90 is the $1 MINIMUM commission × 4 fills.
  - Tradable pairs per month fall from 8.7 to 6.3. top_n = 5 still mostly fills.
  - Killed entirely: HYG-JNK (was the #1 pair), IEF-TLT, LQD-TLT, SHY-IEF, SHY-TLT, TIP-IEF, TIP-TLT.
    Their spreads move too little to beat 3× costs on $1,000 legs.
  - Lever: bigger legs. The minimum commission is fixed, so its share of cost falls as legs grow.
  - The kill/continue CSV predates the hurdle; rerun formation_scan to refresh it.
- Z-SCORE METHOD TEST (train, 838 tradable pair-months, next 21 trading days after each refit):
  - Formation's drift barely persists: next-month slope = 0.18 × formation slope (1 = persists,
    0 = noise). Projecting the line misses next month's centre by 0.98σ vs 0.96σ for a flat line.
  - Out-of-sample z (median |avg z| / drift-side bias / days beyond ±2, ideal ≈ 0 / 0 / 4.6%):
    A N=10 0.40/+0.07/5.9% · A N=20 0.68/+0.12/10.6% · A N=60 1.04/+0.39/14.8% ·
    B line 0.98/−0.34/21.8% · C N=10 0.42/−0.11/5.9% · C N=20 0.73/−0.17/11.1% · C N=40 0.94/−0.22/13.5%.
  - B worst (projects a drift that stops). C over-corrects (bias flips negative), no better than A.
    Lookback length matters more than the method. → Option A chosen.
  - Per-pair thresholds not needed: each pair's 95th-pct |z| in its formation year is 1.93–2.10 at
    N=10 (2.09–2.36 at N=20), and a pair's own level doesn't predict next month (correlation 0.00).
- REGIME vs FIXED THRESHOLDS (crude preview, NOT a backtest: 410 first-entries at |z| ≥ 2, selected
  pairs, N=20, stop 3.5, time stop 3×HL, $1,000 legs, train; regime = SPY 20-day vol terciles):
  - Calm / normal / volatile: profit-exit 57% / 62% / 57%, stop 12% / 16% / 11%, time stop 31% / 22% / 31%.
    In z units the outcomes barely change by regime → the rolling z already absorbs market volatility.
  - Spread vol barely moves with market vol (median 0.47% / 0.51% / 0.51%): the pairs are hedged.
  - ⚠ Net per trade NEGATIVE in every regime (−0.51% / −0.36% / −0.50%), win rate 37–44%.
    Round-trip cost ≈ 1.0 × the rolling 20-day spread σ: costs eat about half of a 2σ → 0 trade.
  - σ MISMATCH (FIXED): the hurdle used the 12-month σ (median 1.18%) but trades fire on the 20-day σ
    (~0.5%), so it approved pairs on a move the strategy never trades. Now uses the typical 20-day σ.
    Effect (16 sampled train refits, $1,000 legs): 4.9 tradable per refit with costs ON (4.7 rejected
    for cost) vs 9.6 with costs OFF. top_n = 5 now often doesn't fill → leg size in sizing.py matters.
  - Conclusion: levels should adapt, but to COST/σ (per pair, per day), not to market regime.

## Open / TBD (resolve on TRAIN data only, before validation)
- z-score lookback N (config signal.zscore_lookback, starting 20): choose by backtest, try 15–30.
  Final pick on backtest profit, NOT on "average z ≈ 0" (short N always looks centred because it hugs the spread).
- Signal thresholds (entry ±2, exit 0, stop ±3.5, time stop 3× HL): starting values, tune by backtest.
  A regime switch (e.g. wider entry when overall vol is high) is a later experiment, after the baseline.
- Kalman δ and observation variance
- Breakdown settings: starting values set from simulation (252 / 0.30 / weekly / k=3); confirm in the
  backtest along with force_close vs hold.
- Leg concentration: HYG sits in the selected top 5 in 92% of months, LQD 72%, JNK 66%. The top 5
  is often one credit bet three ways. Cap how many selected pairs may share a leg? (e.g. max 2)
- DEFERRED (config `multiple_testing: none` for now): how to handle the ~4 fake passes per refit
  (72 pairs × ~6%). Read the kill/continue pass counts with this in mind. Options:
  - Longer window for the cointegration TEST only (config test_window_months; β still from lookback_months). Simulated, trend="ct":
    252d catches HL10 38% / HL20 17%; 504d catches HL10 90% / HL20 42%. Fake rate ~6–8% either way.
  - Persistence: pass in k of the last m formations. Weaker than it looks: monthly windows share
    ~90% of their data, so fake passes persist too.
  - Multiple-testing correction across the 72 (e.g. Benjamini-Hochberg).
  - trend="c" is NOT an option: on drifting spreads it misses most real pairs (18% at HL10).

## Live readiness (spec only, DO NOT BUILD until the paper-trading stage)
The runner alone doesn't trade: with every helper built and live mode on, it stages one day of
orders and exits. These are needed before paper/live. Rules marked TBD are decided later.
- Daily data refresh: pull today's close into ROME.duckdb before prices are loaded (placeholder: pull_today_prices in run setup). Backtests keep
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
- Currency: the account is in CAD and the ETFs trade in USD. Costs handle it via config costs.fx_bps
  (0 = USD held in the account). Sizing still needs a CAD→USD conversion for capital. TBD.
- Kill switch: TBD drawdown / daily-loss limit that halts new entries. Must exist before real money.

## Build order / status
- [x] Data layer
- [ ] runner.py (draft 3: no step(), inline daily loop A–D, calls engine; real code gets filled in as the modules it calls are built)
- [x] Pair list: LOCKED at 72 pairs (data/store/universes/ROME_pairs.csv). Final, no cuts.
- [x] stats.py (hedge_ratio, cointegration, half_life; checked on simulated data)
- [x] formation.py (tested: synthetic cases + look-ahead pass; preliminary real run on 21 pairs)
- [x] Re-pull the short-history symbols for 2010–now
- [x] Full formation run on 2012–19, all 72 pairs (kill/continue gate) → CONTINUE
- [x] engine.py skeleton (decide_targets moved out of the runner; pseudocode)
- [x] costs.py (cost hurdle in formation now live; cost settings are unverified estimates)
- [x] spread.py (hand check + formation cross-check pass)
- [x] z-score method decided: option A (train-data test)
- [x] zscore.py (wired into engine step 3; engine passes z_today, NaN if a leg has no price today)
Phase 1, strategy side:
- [x] breakdown.py + stats.adf_pvalue (wired into engine step 4; State parts still pseudocode)
- [x] signals.py (wired into engine step 5; state values still placeholders; engine uses min_notional_per_leg for today's cost until sizing exists)
- [ ] sizing.py (leg size, shared-ticker cap)
- [ ] fill in engine (pairs_to_manage, hedge_for) → look-ahead test
Phase 2, execution + backtest:
- [ ] models.State + state_mgmt.py + ROME trade log (state always rebuilt from the log)
- [ ] trades.py (targets − holdings; adds targets per TICKER: shared-legs rule)
- [ ] portfolio.py + sim_broker.py (next-open fills, charged via costs.fill_cost / borrow_cost)
- [ ] backtest = runner in backtest mode (fill in open_prices, make_calendar, is_refit_day). No separate harness
- [ ] report.py (reads the trade log only)
- [ ] GATE: train backtest after costs. Poor net Sharpe → stop here
Phase 3, improvement:
- [ ] kalman.py → compare OLS vs Kalman
Phase 4, live path:
- [ ] ibkr_broker.py (same interface as sim_broker, plus approve/veto)
- [ ] everything under "Live readiness"
- [ ] paper trading + parity test
- [ ] holdout (once) → live at 1/3 size

## Required tests
- Look-ahead: output at t is identical whether computed on data truncated at t or on the full data.
- Idempotency: the same targets sent twice produce zero orders.
- Frozen β: an open trade's exit uses its entry β.
- Gap fill: fills happen at the open, not at the stop level.
- Parity: replaying N paper-trading days through the backtest gives identical targets.