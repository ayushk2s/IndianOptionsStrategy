# NIFTY / BANKNIFTY Weekly Options — Backtest Study (2020–2024)

A **research and teaching** repository: what actually happens when you
systematically buy or sell NIFTY / BANKNIFTY weekly options, backtested on
1-minute data with a full Indian cost model — and, just as importantly, **how a
backtest can lie to you**.

> **This is not a signal service and contains no deployable money-making edge.**
> Most of the strategies here lose money. The value is the *method*, the *cost
> model*, and a real, worked example of **look-ahead bias** turning a losing
> strategy into a fake "100% win rate".

---

## TL;DR — results (net of brokerage, STT, exchange, GST, stamp, SEBI, slippage)

| Strategy | Type | Honest verdict |
|---|---|---|
| Buy ATM call / put / straddle (weekly or expiry-day) | Buying | **Loses.** 6 of 8 buying variants negative; avg buyer win rate ~30%. |
| Buy OTM put −50 | Buying | Marginal (+~18% in 2024) — but only because of one crash month. Not robust. |
| Iron condor (ATM short + 100-pt wings) | Selling | **Loses.** Wings cost more than the protection is worth at this width. |
| **Short strangle** (sell ~200-pt OTM CE+PE, hold to expiry) | Selling | **The only structurally sound idea.** ~63–80% win rate; positive but with a fat left tail — one bad week wipes several good ones. Needs stops / defined risk. |
| 0DTE short straddle (2× per-leg stop) | Selling | **~2% CAGR** combined NIFTY+BANKNIFTY, 2020–2024. Below a fixed deposit. Decaying (all the gains were 2020–21). Not usable. |
| **"Opening Spike Fade"** (sell the 09:15 auction spike) | Microstructure | **NOT a real edge — look-ahead bias.** See below. |

---

## The centrepiece lesson: look-ahead bias

The original notes claimed the "Opening Spike Fade" had a **100% win rate** and
made **+₹4,35,300** in one year. That result comes from an entry rule of the form:

```
enter IF (09:15 open − 09:15 close) > ₹8
```

The **close of the 09:15 candle is not known until 09:16.** You cannot use it to
decide a trade at 09:15. The filter is silently selecting only the trades where
the price *already fell within that minute* — so buying it back at the (lower)
close is trivially profitable. Hence 100%.

Re-tested honestly — sell the near-ATM CE + PE at the 09:15 open, buy back at the
**09:16 open**, every day, no filter:

| | trades | win rate | total P&L | t-stat |
|---|--:|--:|--:|--:|
| NIFTY — honest, 2022–24 | 1,402 | 42.6% | **−₹77,665** | **−3.8** (significantly negative) |
| NIFTY — with the look-ahead filter | 486 | **100%** | +₹223,112 | +25.9 |
| BANKNIFTY — honest, 2022–24 | 1,402 | 49.2% | +₹33,045 | 0.8 (statistically zero) |

**Run it yourself:** [`look_ahead_bias_demo.py`](look_ahead_bias_demo.py) is a
self-contained ~180-line script that reproduces both columns side by side (point
`BASE` at your minute data; it explains what it would show if the data is
absent).

**Traded for real, NIFTY loses money with high significance; BANKNIFTY is
indistinguishable from noise (median trade is negative).** The eye-catching
number was entirely an artifact.

> **Rule of thumb: a backtested "100% win rate" is almost always a bug, not an
> edge.** Usually look-ahead bias, survivorship bias, or a selection filter that
> uses future information.

---

## What you can learn from this repo

1. **How to build a bias-free options backtest.** Signal at bar close → fill at
   the *next* bar; never use a bar's own close (or later bars) in the entry
   decision; settle expired legs at intrinsic, not at a stale quote.
2. **A realistic Indian F&O cost model** (`fees_config.py`): ₹20/order brokerage,
   STT 0.05–0.15% on the sell side, NSE transaction charge, SEBI turnover fee,
   stamp duty on the buy side, 18% GST on (brokerage + exchange charge), plus
   per-side slippage and a latency buffer. Multi-leg trades multiply order count.
3. **Option *buyers* lose systematically** on weekly NIFTY (2020–2024): ~70% of
   premium paid expires worthless. The mirror image — disciplined selling — is
   where the (small, risky) edge is.
4. **The volatility risk premium is real but thin.** Weekly options implied
   ~2.5–3% moves; realised was ~1–2%. Sellers harvest that gap — and give a lot
   of it back on gap events (Oct-2024 crash, election week, global risk-off).
5. **Expiry-day / 0DTE options are lottery tickets for buyers** (~27% win, ~100%
   loss when they miss) and a **theta-thin, gamma-heavy** trade for sellers —
   the 0DTE short straddle here barely clears zero after costs.
6. **Iron condors need wide wings.** ATM-short with 100-pt wings gets breached
   almost every other week; the premium collected does not cover it.
7. **Why "it worked in 2024" is not enough.** Several strategies here were only
   positive because of one or two exceptional months. Always look at the
   per-month / per-year breakdown, not just the total.
8. **How to sanity-check your own backtest**: run the strategy with the entry
   filter *removed* — if the edge disappears, the filter was doing the work, and
   you need to check whether that filter is realisable in real time.

---

## Repository contents

```
fees_config.py                        Indian F&O cost model (see above)
NIFTY_Options_Strategies_2024.md      original 2024 notes (13 strategies A–M)
                                      — read with the caveats in this README
options_backtest/
  backtest_nifty_options.py           8 option-buying strategies
  strategy_0dte_straddle.py           0DTE short straddle, NIFTY+BNF, 2020–2024,
                                      2× per-leg stop  (the only fully current script)
mismatch_arb/
  backtest_mismatch.py                short strangle, iron condor, spike fade
```

### Known issues (be honest if you fork this)

* `backtest_nifty_options.py` and `backtest_mismatch.py` were written for an
  older data layout — files named `NIFTY-{EXPIRY}-{TRADEDATE}.csv` with columns
  `datetime, strike_price, right`. They will **not run** on the common
  `date,time,symbol,open,high,low,close,oi,volume` (symbol = `NIFTY04JAN2418300CE`)
  format without a loader rewrite. Only `strategy_0dte_straddle.py` uses the
  current format.
* The numbers in `NIFTY_Options_Strategies_2024.md` are single-year (2024) and,
  for the spike fade, look-ahead-biased. Treat them as illustrative, not as
  expected returns.

---

## Data

NIFTY & BANKNIFTY 1-minute bars — **spot** (index), **futures** (continuous
front-month), and **options** (per contract, weekly expiry, ~0–6 DTE), 2020-01 to
2024-10. Not included in this repo. Public/paid sources exist for NSE
minute-level F&O data.

Expected layout for `strategy_0dte_straddle.py`:

```
<DATA>/nifty_data/nifty_options/<YYYY>/<M>/nifty_options_<DD_MM_YYYY>.csv
<DATA>/nifty_data/nifty_spot/<YYYY>/<M>/nifty_spot<DD_MM_YYYY>.csv
<DATA>/banknifty_data/...  (analogous)
```
Set the `BASE` path at the top of the script.

---

## Running

```bash
python -m venv .venv && . .venv/Scripts/activate   # (or source .venv/bin/activate)
pip install pandas numpy

# 0DTE short straddle, NIFTY + BANKNIFTY, 2020–2024
python options_backtest/strategy_0dte_straddle.py
```

Set `PYTHONIOENCODING=utf-8` on Windows if the box-drawing characters error.

---

## Disclaimer

Educational and research use only. Backtested results on historical data are not
indicative of future performance. Options selling carries unlimited / large
downside risk. Nothing here is investment advice. Do your own testing, paper-trade
first, and size for the worst week you can imagine — then double it.
