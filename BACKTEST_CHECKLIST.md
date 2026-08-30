# Backtest sanity checklist

A short, practical list distilled from the mistakes documented in this repo. Run
through it before you believe *any* options/futures backtest — your own or
someone else's.

## Look-ahead bias

- [ ] **Does any entry/exit decision use a value from the same bar it trades on,
      or a later bar?** Classic trap: filtering on a candle's `close` (or `high`
      / `low`) to decide a trade at that candle's `open`. You only know the open
      in real time.
- [ ] **Signal at bar `t` → fill at bar `t+1`.** Never fill at the price that
      produced the signal.
- [ ] **Remove your entry filter and re-run.** If the edge vanishes, the filter
      was doing the work — now check whether that filter is computable in real
      time. (This repo's `look_ahead_bias_demo.py` does exactly this.)
- [ ] Rolling features (`.rolling(...).mean()`, z-scores, channels) — are they
      shifted so bar `t` only sees bars `≤ t-1` where required?
- [ ] Are option strikes / expiries chosen from data available *at the decision
      minute*, not from the end-of-day or the settlement price?

## "Too good" signals

- [ ] **A ~100% win rate is a bug until proven otherwise.** Usually look-ahead,
      survivorship, or a selection filter using future info.
- [ ] Sharpe > ~2 on a simple retail strategy after real costs → re-check costs
      and leakage.
- [ ] Equity curve with no meaningful drawdowns → you are probably not modelling
      losses (e.g. expired legs settled at a stale quote instead of intrinsic).

## Costs & fills (Indian F&O)

- [ ] Brokerage per *order* × number of legs × (entry + exit).
- [ ] STT on the **sell** side of the premium; stamp duty on the **buy** side.
- [ ] Exchange transaction charge + SEBI turnover fee + 18% GST on
      (brokerage + exchange charge).
- [ ] Slippage **per side per leg**, wider for OTM and for BANKNIFTY; add a
      latency buffer.
- [ ] Multi-leg structures (iron condor = up to 8 orders) — cost scales fast.
- [ ] Expired options settle at **intrinsic value**, not at the last traded (and
      possibly stale) quote.

## Sample & regime

- [ ] **One good year is not a backtest.** Look at every month and every year
      separately. Several strategies here were only positive because of one or
      two exceptional months (May-2024 election, Oct-2024 crash).
- [ ] Is the sample long enough for the number of independent trades to matter?
      A weekly strategy over 2 years is ~100 trades — a small sample.
- [ ] Was the calibration period (in-sample) separate from the evaluation period
      (out-of-sample)? Parameters tuned on the same data you report on = overfit.
- [ ] Does the strategy survive a stress test: 2× slippage, 2× costs, entry a
      minute later?

## Survivorship / selection (matters more for equities, but check)

- [ ] Is the instrument universe *point-in-time*, or is it today's list applied
      to the past? (Delisted / demoted names being absent inflates results.)
- [ ] For continuous futures, is the roll modelled (cost + no dividends)?

## Risk

- [ ] What is the **worst single week / day** in the backtest, as a % of the
      capital or margin actually deployed? Assume the real worst is bigger.
- [ ] For short options: is the loss bounded (spread) or unbounded (naked)? Size
      for a 3–5× premium spike week.
- [ ] Is the margin model realistic? SPAN + exposure margin rises in stress —
      exactly when you are losing.
