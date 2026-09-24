# ROME test plan

Five tests. Each one guards a specific way this strategy could lie to me.

## 1. Look-ahead
Output at `t` must be **identical** whether the engine is fed data truncated at
`t` or the full history. Run over many `t`. Any difference means something is
peeking at the future.

## 2. Backtest/live parity
Replay N paper-traded days through the backtest. The **targets must match
exactly**. A mismatch means the two paths diverged, and the backtest no longer
describes the live system.

## 3. Idempotency
Send the same targets to the broker twice. The second call must produce **zero
trades**. This is what makes a crashed live run safe to restart.

## 4. Frozen beta
Open a trade, let the pair's beta move, then exit. The exit must be computed
with the **entry** beta — the position actually held.

## 5. Next-open fill with a gap
Construct a gap through the stop level. The fill must land at the **open**, not
at the stop price. A backtest that fills at the stop is inventing money.

---

Each test names the bug it prevents. If a test is hard to write, that usually
means the code under it is doing too much.
