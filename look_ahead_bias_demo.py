"""
look_ahead_bias_demo.py
=======================
A self-contained, runnable demonstration of LOOK-AHEAD BIAS — the single most
common way an options backtest lies to you.

THE STRATEGY UNDER TEST — "Opening Spike Fade"
---------------------------------------------
Folklore: in the first traded minute of the day (09:15) the pre-market auction
leaves some option quotes far from fair value. Sell the ones that "spiked", buy
them back a minute later when the price normalises.

THE BUG
-------
The classic implementation enters a trade only when

        (09:15 open price) - (09:15 CLOSE price) > threshold

but the CLOSE of the 09:15 candle is not known until 09:16. Using it to pick
trades at 09:15 is look-ahead bias: the filter is quietly keeping only the
trades where the price ALREADY fell inside that minute, so buying them back at
the lower close is guaranteed profit. Result: a fake ~100% win rate.

WHAT THIS SCRIPT DOES
---------------------
Runs the SAME strategy two ways and prints both:

  HONEST : sell CE+PE at the 09:15 open, buy back at the 09:16 OPEN, EVERY day,
           no filter. This is all a real trader can do.
  CHEAT  : keep only trades where (open - close_of_that_minute) > threshold.
           This peeks at information you don't have yet.

If the edge only exists in the CHEAT column, it is not real.

DATA (not included in the repo)
-------------------------------
NSE 1-minute option + futures bars, layout:

  <BASE>/nifty_data/nifty_options/<YYYY>/<M>/nifty_options_<DD_MM_YYYY>.csv
  <BASE>/nifty_data/nifty_fut/<YYYY>/<M>/nifty_fut_<DD_MM_YYYY>.csv

  columns: date,time,symbol,open,high,low,close,oi,volume
  option symbol: NIFTY04JAN2418300CE  (UND + DDMMMYY expiry + strike + CE/PE)

Set BASE below. If the data is absent the script explains what it would show and
exits cleanly.

    python look_ahead_bias_demo.py
"""
from __future__ import annotations

import calendar
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
BASE = Path(r"C:\Users\GIGA\Documents\Nifty_BankNifty_O_F_DATA")   # <-- set me
UNDERLYING = "NIFTY"          # "NIFTY" or "BANKNIFTY"
YEARS = [2022, 2023, 2024]
SPIKE_THRESHOLD = 8.0         # Rs, the (bogus) entry filter
LOT = {"NIFTY": 25, "BANKNIFTY": 15}[UNDERLYING]
STRIKE_STEP = {"NIFTY": 50, "BANKNIFTY": 100}[UNDERLYING]

# realistic all-in cost for one option leg (buy + sell), per the repo's fee model
BROKERAGE_PER_ORDER = 20.0
STT_SELL = 0.0015
EXCH = 0.00035
SEBI = 10 / 1e7
STAMP = 0.00003
GST = 0.18
SLIPPAGE_PTS_PER_SIDE = 1.0
LATENCY_PTS = 0.25
_MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}
_SYM = re.compile(r"^(NIFTY|BANKNIFTY)(\d{2})([A-Z]{3})(\d{2})(\d+)(CE|PE)$")


def leg_cost(sell_px: float, buy_px: float, qty: int) -> float:
    st, bt = sell_px * qty, buy_px * qty
    brokerage = BROKERAGE_PER_ORDER * 2
    exch = (st + bt) * EXCH
    return (brokerage
            + st * STT_SELL
            + exch
            + (st + bt) * SEBI
            + bt * STAMP
            + (brokerage + exch) * GST)


def _day_file(stream: str, day: pd.Timestamp) -> Path:
    u = UNDERLYING.lower()
    stub = f"{u}_{'options' if stream == 'options' else 'fut'}_{day:%d_%m_%Y}.csv"
    if stream == "options":
        stub = f"{u}_options_{day:%d_%m_%Y}.csv"
    return BASE / f"{u}_data" / f"{u}_{stream}" / f"{day.year}" / f"{day.month}" / stub


def _load(stream: str, day: pd.Timestamp) -> pd.DataFrame:
    p = _day_file(stream, day)
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"])
    return df


def _list_option_days() -> list[pd.Timestamp]:
    root = BASE / f"{UNDERLYING.lower()}_data" / f"{UNDERLYING.lower()}_options"
    days = []
    for p in root.glob("*/*/*.csv"):
        m = re.search(r"(\d{2})_(\d{2})_(\d{4})\.csv$", p.name)
        if m:
            d, mo, y = map(int, m.groups())
            if y in YEARS:
                days.append(pd.Timestamp(year=y, month=mo, day=d))
    return sorted(days)


def summarise(name: str, pnl: list[float]) -> None:
    p = np.array(pnl, float)
    if len(p) == 0:
        print(f"  {name:22s} no trades")
        return
    t = p.mean() / (p.std(ddof=1) / np.sqrt(len(p))) if len(p) > 2 else 0.0
    print(f"  {name:22s} n={len(p):5d}  win={100*(p>0).mean():5.1f}%  "
          f"totalP&L=Rs {p.sum():>11,.0f}  avg=Rs {p.mean():>7.1f}  "
          f"median=Rs {np.median(p):>7.1f}  t-stat={t:>6.2f}")


def main() -> int:
    if not BASE.exists():
        print(__doc__)
        print(f"\n[data not found at {BASE}]")
        print("Set BASE to your NSE 1-minute F&O data directory and re-run.")
        print("\nWhat you WOULD see (from the study this repo documents):")
        print("  HONEST : NIFTY 2022-24  win 42.6%  total -Rs 77,665  t-stat -3.8  (loses, significantly)")
        print("  CHEAT  : NIFTY 2022-24  win 100.0% total +Rs 223,112 t-stat +25.9 (fake — look-ahead)")
        return 0

    days = _list_option_days()
    if not days:
        print(f"[no option files for {YEARS} under {BASE}]")
        return 1

    honest: list[float] = []
    cheat: list[float] = []

    for day in days:
        fut = _load("fut", day)
        opt = _load("options", day)
        if fut.empty or opt.empty:
            continue

        t0 = pd.Timestamp.combine(day, pd.Timestamp("09:15").time())
        t1 = pd.Timestamp.combine(day, pd.Timestamp("09:16").time())

        f_at_open = fut.loc[fut["ts"] <= t0, "close"]
        if f_at_open.empty:
            continue
        atm = round(float(f_at_open.iloc[-1]) / STRIKE_STEP) * STRIKE_STEP

        meta = opt["symbol"].map(lambda s: _SYM.match(s))
        opt = opt.assign(
            strike=meta.map(lambda m: int(m.group(5)) if m else np.nan),
            right=meta.map(lambda m: m.group(6) if m else None),
            expiry=meta.map(lambda m: pd.Timestamp(
                year=2000 + int(m.group(4)), month=_MONTHS[m.group(3)],
                day=int(m.group(2))) if m else pd.NaT),
        )
        near_expiry = opt["expiry"].dropna().min()
        chain = opt[opt["expiry"] == near_expiry]

        for right in ("CE", "PE"):
            leg = chain[(chain["strike"] == atm) & (chain["right"] == right)]
            row0 = leg[leg["ts"] == t0]
            row1 = leg[leg["ts"] == t1]
            if row0.empty or row1.empty:
                continue

            open_px = float(row0.iloc[0]["open"])
            close_px = float(row0.iloc[0]["close"])   # NOT known at 09:15:00
            next_open = float(row1.iloc[0]["open"])    # first price you can act on
            if open_px <= 1.0:
                continue

            # sell at the open, buy back at the next real price — full costs
            gross = (open_px - next_open) * LOT
            costs = leg_cost(open_px, next_open, LOT)
            slip = 2 * (SLIPPAGE_PTS_PER_SIDE + LATENCY_PTS) * LOT
            pnl = gross - costs - slip

            honest.append(pnl)                         # every day, no filter
            if (open_px - close_px) > SPIKE_THRESHOLD:  # <-- the look-ahead filter
                cheat.append(pnl)

    print("=" * 78)
    print(f"  OPENING SPIKE FADE  --  {UNDERLYING}  --  {YEARS[0]}-{YEARS[-1]}")
    print("  sell ATM CE+PE at 09:15 open, buy back at 09:16 open, full costs")
    print("=" * 78)
    summarise("HONEST (no filter)", honest)
    summarise("CHEAT (peeks at close)", cheat)
    print()
    if honest and cheat:
        hp, cp = np.array(honest), np.array(cheat)
        print(f"  The 'edge' is entirely the filter: honest mean Rs {hp.mean():.1f}/trade "
              f"vs cheat mean Rs {cp.mean():.1f}/trade.")
        print(f"  The cheat keeps {len(cheat)}/{len(honest)} trades — only the ones that "
              f"already moved your way inside the 09:15 minute.")
        print("  A backtested ~100% win rate is a red flag, not a discovery.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
