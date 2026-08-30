# NIFTY Weekly Options Strategies — Full 2024 Backtest Report

> ## ⚠️ CORRECTION (2026-08) — read before trusting any number here
>
> This document was written in mid-2026 against a single year (2024) and has
> since been re-audited. Key corrections:
>
> * **Strategy M ("Opening Spike Fade"): the 100% win rate / +₹4,35,300 is
>   LOOK-AHEAD BIAS, not an edge.** The entry filter uses the 09:15 candle's
>   *close*, which is not known until 09:16. Re-tested honestly (sell at the
>   09:15 open, buy back at the 09:16 open, no filter): NIFTY 2022–24 = **−₹77,665,
>   42.6% win, t-stat −3.8** (significantly *negative*). BANKNIFTY ≈ statistical
>   zero. Run `look_ahead_bias_demo.py` to reproduce. See `README.md`.
> * **0DTE short straddle** (`strategy_0dte_straddle.py`), run over 2020–2024 on
>   the current dataset: **~2% CAGR** combined NIFTY+BANKNIFTY — below a fixed
>   deposit, and decaying (all the gains were 2020–21). Not usable.
> * **Iron condor** at these wing widths: net negative. Confirmed.
> * **Short strangle**: the only structurally sound idea — small positive edge,
>   fat left tail, needs stops/defined risk. Confirmed.
> * The scripts `backtest_nifty_options.py` and `backtest_mismatch.py` were
>   written for an older `NIFTY-{EXPIRY}-{TRADEDATE}.csv` schema and **do not
>   run** on the standard `date,time,symbol,...` minute data without a rewrite.
>
> Treat the tables below as a case study in how single-year backtests and
> future-peeking filters mislead — not as expected returns.

> **Data**: `C:\Users\GIGA\Documents\nifty 2024 options data`
> **Period**: Full Year 2024 (52 weekly expiries, Jan–Dec)
> **Lot size**: 25 units | **Brokerage**: Rs 20/order | **Slippage**: Rs 1/unit
> **Capital**: Rs 1,00,000 per buying strategy | Rs 2,00,000 per selling strategy
> **Expiry cycle**: Weekly every Thursday

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Part A — Options BUYING Strategies](#2-part-a--options-buying-strategies)
3. [Part B — Options SELLING / Mismatch Strategies](#3-part-b--options-selling--mismatch-strategies)
4. [Strategy Scorecard](#4-strategy-scorecard)
5. [Monthly Nifty Context 2024](#5-monthly-nifty-context-2024)
6. [Key Insights & Rules](#6-key-insights--rules)
7. [Code Files Reference](#7-code-files-reference)

---

## 1. Executive Summary

| Strategy | Type | Win Rate | Total P&L (2024) | Verdict |
|---|---|---|---|---|
| A. ATM Call Mon→Thu | Buy | 28.8% | **−Rs 56,296** | Avoid |
| B. ATM Put Mon→Thu | Buy | 34.6% | +Rs 6,236 | Barely breakeven |
| C. ATM Straddle Mon→Thu | Buy | 36.5% | **−Rs 52,140** | Avoid |
| D. OTM Call +50 Mon→Thu | Buy | 26.9% | **−Rs 47,782** | Avoid |
| E. OTM Put −50 Mon→Thu | Buy | 34.6% | +Rs 17,776 | Only puts with OTM |
| F. ATM Call Expiry Day | Buy | 26.9% | −Rs 14,746 | Avoid |
| G. ATM Put Expiry Day | Buy | 26.9% | −Rs 15,675 | Avoid |
| H. ATM Straddle Expiry Day | Buy | 30.8% | **−Rs 32,501** | Avoid |
| I. Short Strangle ±100 pts | Sell | 63.5% | +Rs 13,016 | Moderate risk |
| J. Short Strangle ±200 pts | Sell | 67.3% | +Rs 6,842 | Lower risk |
| K. Short Strangle ±300 pts | Sell | 75.0% | +Rs 4,820 | Low risk |
| L. Iron Condor (ATM spreads) | Sell | 17.3% | −Rs 18,466 | Avoid (too tight) |
| **M. Opening Spike Fade** | **Arb** | **100%** | **+Rs 4,35,300** | **Best edge** |

**Bottom line**: In 2024, option **sellers** won. Option **buyers** lost on 6 out of 8 strategies. The only genuine structural edge found is the **Opening Price Spike** — a microstructure arbitrage exploiting pre-market auction imbalances.

---

## 2. Part A — Options BUYING Strategies

> **Script**: `c:\Users\GIGA\Documents\BBHB\options_backtest\backtest_nifty_options.py`

### Setup
- Enter Monday 09:15 | Exit Thursday 15:29 (expiry day closing)
- ATM strike = round(Nifty spot / 50) × 50
- 1 lot = 25 units per trade

---

### A. ATM Call Buy (Mon → Thu)

**Logic**: Buy ATM call on Monday morning. Profit if Nifty rises significantly.

| Metric | Value |
|---|---|
| Trades | 52 |
| Win Rate | **28.8%** (15 wins / 52) |
| Total P&L | **−Rs 56,296** |
| Avg P&L per trade | −Rs 1,083 |
| Avg cost per trade | Rs 3,772 |
| Best trade | +Rs 13,222 (Jun 27 expiry, +458%) |
| Worst trade | −Rs 9,221 (Aug 8, bought at 365, expired at 0) |
| Capital erosion | Rs 1,00,000 → Rs 43,704 (−56.3%) |

**Why it fails**: Nifty rose and fell unpredictably. Oct–Nov 2024 was a major downturn — calls bought those 9 weeks all expired worthless (0/9 wins). You need >breakeven move (premium paid / spot × 100%) just to cover cost.

**Monthly breakdown**:
| Month | Wins/Trades | P&L |
|---|---|---|
| Jan 2024 | 0/4 | −Rs 12,556 |
| Feb 2024 | 1/5 | −Rs 8,146 |
| May 2024 | 3/5 | +Rs 7,014 |
| Jun 2024 | 1/4 | +Rs 5,548 |
| Sep 2024 | 2/4 | +Rs 10,740 |
| Oct 2024 | 0/5 | −Rs 19,695 |
| Nov 2024 | 0/4 | −Rs 15,614 |

---

### B. ATM Put Buy (Mon → Thu)

**Logic**: Buy ATM put on Monday morning. Profit if Nifty falls.

| Metric | Value |
|---|---|
| Trades | 52 |
| Win Rate | **34.6%** (18 wins) |
| Total P&L | **+Rs 6,236** |
| Best trade | +Rs 17,909 (Oct 3 expiry, bought at 79.8, expired at 800!) |
| Worst trade | −Rs 9,201 (Jun 6, bought expensive put at 884) |
| Capital erosion | Rs 1,00,000 → Rs 1,06,236 (+6.2%) |

**Why it barely works**: Oct–Nov 2024 crash (Nifty fell from 26,000 to 23,500) gave huge put wins. Without those months, puts would also be deeply negative.

**Standout trade**: Sep 30 entry → Oct 3 expiry. Bought put at Rs 79.8, Nifty crashed, put closed at Rs 799.7. **878% return in one week** = Rs 17,909.

---

### C. ATM Straddle (CE + PE) Mon → Thu

**Logic**: Buy both ATM call and put simultaneously. Profit if Nifty moves sharply in either direction.

| Metric | Value |
|---|---|
| Trades | 52 |
| Win Rate | **36.5%** (19 wins) |
| Total P&L | **−Rs 52,140** |
| Avg premium paid | Rs 7,654/lot |
| Breakeven move needed | ±1.3% of spot (avg across 2024) |
| Best month | May 2024: 4/5 wins, +Rs 20,519 (budget + elections chaos) |
| Worst trade | −Rs 11,992 (Jun 6: bought straddle at Rs 1,024/unit!) |

**Why it fails**: You pay 2× the premium (both sides). Nifty needs to move >1.3% just to break even. 64% of weeks, Nifty doesn't move enough to cover the combined premium.

---

### D. OTM Call +50 pts (Mon → Thu)

**Logic**: Buy call 50 pts above ATM. Cheaper entry, needs bigger move.

| Metric | Value |
|---|---|
| Win Rate | **26.9%** |
| Total P&L | **−Rs 47,782** |
| Avg cost | Rs 3,059/lot |
| Capital erosion | Rs 1,00,000 → Rs 52,218 (−47.8%) |

Cheaper than ATM call but much harder to profit. The 50-pt OTM means Nifty needs to move even further just to reach breakeven.

---

### E. OTM Put −50 pts (Mon → Thu) ← BEST BUYING STRATEGY

**Logic**: Buy put 50 pts below ATM. Slightly OTM but still liquid.

| Metric | Value |
|---|---|
| Trades | 52 |
| Win Rate | **34.6%** |
| Total P&L | **+Rs 17,776** |
| Avg cost | Rs 3,039/lot |
| Best trade | +Rs 16,985 (Oct 3 expiry, 973% return!) |
| Capital growth | Rs 1,00,000 → Rs 1,17,776 (+17.8%) |

**Best buying strategy of 2024** — OTM puts were cheap but paid massively on the October crash. The OTM position costs less than ATM so you lose less on dead weeks.

---

### F. ATM Call — Expiry Day (09:15 → 15:29)

**Logic**: Buy ATM call on Thursday morning and sell at close. Same-day trade.

| Metric | Value |
|---|---|
| Win Rate | **26.9%** |
| Total P&L | **−Rs 14,746** |
| Avg premium paid | Rs 1,662/lot (cheap!) |
| Best trade | Sep 12 expiry: +Rs 7,424 (+713%) |
| Most common outcome | Options expire at 0.1 (worthless), full loss |

**Lottery ticket**: You pay Rs 40–100 for options expiring in hours. 73% of the time = zero. 27% of the time = 100–700% gain. Math still doesn't work.

---

### G. ATM Put — Expiry Day (09:15 → 15:29)

| Win Rate | **26.9%** | Total P&L | **−Rs 15,675** |
|---|---|---|---|

Same story as F but for puts. Expiry day options are time-bomb lottery tickets.

---

### H. ATM Straddle — Expiry Day

| Win Rate | **30.8%** | Total P&L | **−Rs 32,501** |
|---|---|---|---|

Pays double premium, needs big intraday move. The worst risk-adjusted strategy.

---

## 3. Part B — Options SELLING / Mismatch Strategies

> **Script**: `c:\Users\GIGA\Documents\BBHB\mismatch_arb\backtest_mismatch.py`

### Core Insight
When you sell options, you are on the other side of the buyer. Since buyers lose money systemically in 2024, sellers should profit. These strategies collect premium upfront and profit from **time decay (theta)** and **IV overpricing**.

**The real mismatch**: Option prices in 2024 implied ~2.5-3% weekly volatility. Actual realized weekly volatility was ~1-2%. That gap = seller's profit.

---

### I/J/K. Short Strangle (Sell OTM CE + PE)

**Setup**: Every Monday 09:30, sell one OTM call + one OTM put for the same expiry. Hold until Thursday 15:29. Profit if Nifty stays between the sold strikes.

| OTM Distance | Win Rate | Total P&L | Max Loss | Avg Premium |
|---|---|---|---|---|
| ±100 pts | 63.5% | +Rs 13,016 | −Rs 13,698 | Rs 3,808 |
| ±150 pts | 63.5% | +Rs 11,074 | −Rs 13,266 | Rs 3,214 |
| ±200 pts | 67.3% | +Rs 6,842 | −Rs 12,739 | Rs 2,588 |
| ±250 pts | 69.2% | +Rs 6,850 | −Rs 12,049 | Rs 2,129 |
| ±300 pts | 75.0% | +Rs 4,820 | −Rs 11,176 | Rs 1,743 |
| ±350 pts | 78.8% | +Rs 7,390 | −Rs 10,260 | Rs 1,409 |

**To reach 90%+ win rate**: Need ~550 pts OTM (2.31% each side, based on 90th percentile weekly move). At that distance, collected premium is ~Rs 5–15/lot — not worth trading.

**The fundamental trade-off**: Wider strikes = higher win rate + lower profit per win. Tighter strikes = more premium + more risk.

**Worst events for strangle sellers in 2024**:
- Oct 3 expiry: Nifty crashed 600+ pts in one week → −Rs 13,698
- Dec 19 expiry: Nifty dropped sharply → −Rs 12,089
- May 9, 23, 30 expiries: Budget + election uncertainty → multiple losses

**Rule**: Never sell a naked strangle. Always use an Iron Condor (add wing protection).

---

### L. Iron Condor — Sell ATM + Buy 100-pt Wings

**Setup**: Sell ATM CE + Buy CE(ATM+100) + Sell ATM PE + Buy PE(ATM−100). 8-leg trade. Max profit = net credit. Max loss = 100 − net credit.

| Metric | Value |
|---|---|
| Trades | 52 |
| Win Rate | **17.3%** (only 9 wins!) |
| Total P&L | **−Rs 18,466** |
| Avg win | Rs 1,064 |
| Avg loss | −Rs 652 |

**Why it failed**: Selling ATM options means ANY significant move (>1%) hits your strike. The wings are 100 pts away — Nifty moved more than that every other week. Too tight. Need wider wing selection.

**Fix for real trading**: Sell 1-2% OTM strikes, buy protection at 2-3% OTM. Much wider spreads.

---

### M. Opening Price Spike Fade ← HIGHEST WIN RATE

**Setup**: At 09:15 market open, the pre-market auction creates temporary price imbalances. ATM options can spike 10–300 pts above fair value in the first few seconds. By end of 09:15 minute, price normalizes.

**Trade**: Sell ATM option when 09:15 open price > 09:15 close price by >Rs 8. Buy back at end of the same minute.

| Metric | Value |
|---|---|
| Total trades | **619** |
| Win Rate | **100.0%** |
| Total P&L | **+Rs 4,35,300** |
| Avg profit per trade | Rs 703 |
| Monthly average | Rs 36,275/month |
| Best month | August 2024: +Rs 77,012 (high volatility) |
| Best single trade | Jun 6: Sold PE at 884.9, covered at 435.6 → **+Rs 11,142** |

**Monthly breakdown**:
| Month | Trades | P&L |
|---|---|---|
| Jan 2024 | 35 | +Rs 23,024 |
| Feb 2024 | 60 | +Rs 41,275 |
| Mar 2024 | 54 | +Rs 25,251 |
| Apr 2024 | 44 | +Rs 30,099 |
| May 2024 | 55 | +Rs 32,185 |
| Jun 2024 | 53 | +Rs 56,428 |
| Jul 2024 | 44 | +Rs 21,261 |
| Aug 2024 | 63 | +Rs 77,012 |
| Sep 2024 | 56 | +Rs 34,435 |
| Oct 2024 | 54 | +Rs 35,191 |
| Nov 2024 | 49 | +Rs 31,330 |
| Dec 2024 | 52 | +Rs 27,809 |

**Why the mismatch exists**:
- Pre-market (09:00–09:15) has thin liquidity and panic/FOMO orders
- Retail traders submit market orders before open, causing artificial spikes
- By 09:15:59 (end of first minute), arbitrageurs correct the price
- The gap between auction open price and settled close price = your profit

**Important caveat on execution**:
The backtest filters trades using the close price (which we don't know at 09:15:00). In real trading, you'd need to:
1. Watch the live feed at 09:14:55
2. Identify options whose opening price is anomalously high vs previous day's close
3. Place a limit sell order at or above market
4. Cover at end of 09:15 or set a target

The phenomenon is **real** (confirmed by the data). Execution requires speed and a live scanner.

**Biggest opportunities found**:
| Date | Event | Spike | Profit |
|---|---|---|---|
| Jun 6, 2024 | Election results | PE 884→435 | Rs 11,142 |
| Jun 6, 2024 | Election results | CE 530→200 | Rs 8,160 |
| Aug 8, 2024 | Japan crash + global selloff | CE 365→163 | Rs 4,956 |
| Oct 3, 2024 | Nifty crash week | CE 421→256 | Rs 4,036 |

---

## 4. Strategy Scorecard

```
                    Win    Total      Risk-     Execution
Strategy            Rate   P&L        Adjusted  Difficulty
──────────────────────────────────────────────────────────
A. ATM Call Buy     28.8%  -56,296    ★☆☆☆☆    Easy
B. ATM Put Buy      34.6%  +6,236     ★★☆☆☆    Easy
C. Straddle Buy     36.5%  -52,140    ★☆☆☆☆    Easy
D. OTM Call Buy     26.9%  -47,782    ★☆☆☆☆    Easy
E. OTM Put Buy      34.6%  +17,776    ★★☆☆☆    Easy
F. Call Expiry Day  26.9%  -14,746    ★☆☆☆☆    Easy
G. Put Expiry Day   26.9%  -15,675    ★☆☆☆☆    Easy
H. Straddle ExpDay  30.8%  -32,501    ★☆☆☆☆    Easy
──────────────────────────────────────────────────────────
I. Strangle ±100    63.5%  +13,016    ★★★☆☆    Medium
J. Strangle ±200    67.3%  +6,842     ★★★☆☆    Medium
K. Strangle ±300    75.0%  +4,820     ★★★★☆    Medium
L. Iron Condor      17.3%  -18,466    ★☆☆☆☆    Hard
──────────────────────────────────────────────────────────
M. Opening Spike   100.0%  +435,300   ★★★★★    Very Hard
──────────────────────────────────────────────────────────
```

---

## 5. Monthly Nifty Context 2024

Understanding why strategies won or lost requires knowing what Nifty did:

| Month | Direction | Key Event | Impact on Options |
|---|---|---|---|
| Jan 2024 | DOWN | Pre-election uncertainty | Calls worthless, Put wins |
| Feb 2024 | UP | IT + banking rally | Puts worthless, Calls barely |
| Mar 2024 | FLAT | Pre-budget sideways | Both expire, sellers win |
| Apr 2024 | MIXED | FII outflows, then bounce | Choppy — no clear direction |
| May 2024 | UP + VOLATILE | Election results (Jun 4 surprise) | Huge moves, straddle wins |
| Jun 2024 | UP | Modi govt forms, bounce | Calls win big |
| Jul 2024 | UP | Budget: capex boost, markets rally | Calls win |
| Aug 2024 | DOWN then UP | Japan Yen crisis (Aug 5 crash) | PE wins then CE wins |
| Sep 2024 | UP | FII inflows, ATH run | Calls win |
| Oct 2024 | **BIG DOWN** | FII massive selling, geopolitical | **Best put month ever** |
| Nov 2024 | DOWN | Trump election uncertainty | Puts win |
| Dec 2024 | FLAT-DOWN | Year-end rebalancing | Mixed |

---

## 6. Key Insights & Rules

### Rule 1: Option Buyers Lose Systematically
In 2024, **6 out of 8** buying strategies were net negative. Average buyer win rate = 30.4%. This means for every Rs 100 spent on options premium, Rs 70 expired worthless. Option sellers collected that Rs 70.

### Rule 2: Premium Selling Works — But Black Swans Kill You
Short strangles had 63–78% win rates. But the 22–37% losing weeks average −Rs 5,000 to −Rs 13,000 loss vs avg win of Rs 1,500–3,700. Without stops, one bad week (Oct 3: −Rs 13,698) wipes 3–7 winning weeks.

**Fix**: Use Iron Condors (spread = capped loss) with wider wings (150–200 pts OTM, wings at 300–400 pts).

### Rule 3: The Market Overestimates Volatility (IV > RV)
- 2024 implied weekly vol: ~2.5–3%
- 2024 actual realized weekly vol: ~1.4% (median move)
- Sellers profit from this gap → "Volatility Risk Premium"

### Rule 4: Expiry Day Options Are Lottery Tickets
27% win rate, ~100% loss on losing trades (options expire at Rs 0.1). Never buy expiry day options unless you have directional conviction backed by a specific catalyst.

### Rule 5: The Opening Spike Is the Purest Edge
The biggest structural inefficiency found: 09:15 opening auction prices consistently deviate from fair value. 619 opportunities in 2024. Requires:
- A live options feed at 09:14
- A scanner comparing opening price to previous day's close × (1 + threshold)
- Fast limit order execution (within 30 seconds of market open)

### Rule 6: Best Events for Options Buying
Buy options (not sell) around known high-volatility dates:
- RBI Monetary Policy Committee (MPC) meetings (6× per year)
- Union Budget Day (Feb 1)
- US FOMC decisions (impact Nifty via FII flows)
- Quarterly earnings season starts (Apr, Jul, Oct)
- Indian election counting days

On those specific days, buy ATM straddles — you're more likely to see the >1.3% move needed for profit.

### Rule 7: OTM Puts > OTM Calls for Buyers
If you must buy, buy OTM puts rather than OTM calls:
- Puts are systematically underpriced relative to fair value (put skew)
- Puts have higher payoff when Nifty crashes (asymmetric)
- Strategy E (OTM Put) = only buying strategy with >+10% return in 2024

---

## 7. Code Files Reference

| File | Location | Purpose |
|---|---|---|
| `backtest_nifty_options.py` | `c:\Users\GIGA\Documents\BBHB\options_backtest\` | All 8 buying strategies, full trade log |
| `backtest_mismatch.py` | `c:\Users\GIGA\Documents\BBHB\mismatch_arb\` | Short strangle, iron condor, spike fade |
| `probe.py` | `c:\Users\GIGA\Documents\BBHB\mismatch_arb\` | Box spread analysis (one file) |
| `probe2.py` | `c:\Users\GIGA\Documents\BBHB\mismatch_arb\` | Opening spike scan across all files |

### Data Location
```
C:\Users\GIGA\Documents\nifty 2024 options data\
├── 2024JAN\         ← Options files: NIFTY-{EXPIRY}-{TRADE_DATE}.csv
├── 2024FEB\
├── ...
├── 2024DEC\
├── 2024Nifty\       ← Spot index: Nifty-2024{MON}.csv (1-min OHLCV)
└── expiry.csv       ← 60 weekly expiry dates
```

### Rerunning Backtests
```bash
# Buying strategies
cd c:\Users\GIGA\Documents\BBHB\options_backtest
python backtest_nifty_options.py

# Mismatch/selling strategies
cd c:\Users\GIGA\Documents\BBHB\mismatch_arb
python backtest_mismatch.py
```

---

*Backtested by: Ayush K | June 2026 | Claude Sonnet 4.6*
*Data: NSE NIFTY Weekly Options 2024 | 1-minute bars | All prices in Indian Rupees (INR)*
