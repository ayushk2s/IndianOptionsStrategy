"""
backtest_nifty_options.py  --  NIFTY Weekly Options Buying Backtest 2024
=========================================================================
Tests what happens if you BUY NIFTY options every week in 2024.

Data source : C:\\Users\\GIGA\\Documents\\nifty 2024 options data
              1-min OHLCV for each strike on each trade date
              Nifty spot index (1-min) for ATM calculation

Lot size    : 25 units (NIFTY lot size effective Nov 2023)
Expiry cycle: Weekly every Thursday (60 expiries in dataset)
Capital     : Rs 1,00,000 per strategy (1 lakh)

Strategies tested (all LONG options only -- pure buying, no selling):
  A. Buy ATM CALL  on Monday 09:15 | Sell on Expiry 15:29
  B. Buy ATM PUT   on Monday 09:15 | Sell on Expiry 15:29
  C. Buy ATM STRADDLE (CE+PE) Monday 09:15 | Sell both Expiry 15:29
  D. Buy 1-OTM CALL (50 above ATM) Monday 09:15 | Sell Expiry 15:29
  E. Buy 1-OTM PUT  (50 below ATM) Monday 09:15 | Sell Expiry 15:29
  F. Buy ATM CALL  on Expiry day 09:15 | Sell 15:29 (same day lottery)
  G. Buy ATM PUT   on Expiry day 09:15 | Sell 15:29 (same day lottery)
  H. Buy ATM STRADDLE on Expiry day 09:15 | Sell 15:29

Metrics: P&L per trade, Win rate, Max win/loss, CAGR, total 2024 profit
"""

import os, sys, time
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from fees_config import (
    calculate_total_cost, BROKERAGE_PER_ORDER,
    NIFTY_ATM_SLIPPAGE, NIFTY_OTM_SLIPPAGE, LATENCY_BUFFER,
)

DATA_DIR  = Path(r"C:\Users\GIGA\Documents\nifty 2024 options data")
NIFTY_DIR = DATA_DIR / "2024Nifty"
MONTHS    = ["2024JAN","2024FEB","2024MAR","2024APR","2024MAY","2024JUN",
             "2024JUL","2024AUG","2024SEP","2024OCT","2024NOV","2024DEC"]

LOT_SIZE   = 25       # NIFTY lot size 2024
INITIAL    = 100_000  # Rs 1 lakh starting capital

W   = "=" * 80
SEP = "-" * 80


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_dt(s):
    return datetime.strptime(s, "%d%b%y").date()

def atm_strike(spot, interval=50):
    return round(spot / interval) * interval

def load_chain(filepath):
    df = pd.read_csv(filepath, dtype={"datetime": str, "right": str})
    return df

def get_option_px(df, strike, right, minute, col="open"):
    """Get option price at a given minute ('09:15') for a strike/right combo."""
    row = df[(df.strike_price == strike) & (df.right == right) &
             (df.datetime == minute)]
    if row.empty: return None
    return float(row.iloc[0][col])

def load_nifty_spot(trade_date):
    """Return (open, close) for first 09:15 bar of trade_date from monthly file."""
    mon = trade_date.strftime("%Y%b").upper()   # e.g., 2024JAN
    fn  = NIFTY_DIR / f"Nifty-{mon[:4]}{mon[4:]}.csv"
    if not fn.exists():
        fn = NIFTY_DIR / f"Nifty-{mon}.csv"
    if not fn.exists(): return None, None
    df  = pd.read_csv(fn, dtype={"datetime": str})
    date_str = str(trade_date)
    day = df[df.datetime.str.startswith(date_str)]
    if day.empty: return None, None
    spot_open  = float(day.iloc[0]["open"])
    spot_close = float(day.iloc[-1]["close"])
    return spot_open, spot_close


# ── File index ────────────────────────────────────────────────────────────────

def build_index():
    idx = {}  # (expiry_date, trade_date) -> filepath
    by_exp = defaultdict(list)
    for m in MONTHS:
        mdir = DATA_DIR / m
        if not mdir.exists(): continue
        for fname in mdir.iterdir():
            if not fname.suffix == ".csv": continue
            parts = fname.stem.split("-")
            if len(parts) < 3: continue
            try:
                exp = parse_dt(parts[1]); trd = parse_dt(parts[2])
                idx[(exp, trd)] = fname
            except: pass
    for (exp, trd) in idx: by_exp[exp].append(trd)
    for exp in by_exp: by_exp[exp].sort()
    return idx, by_exp


# ── Find entry date (Monday of expiry week) ───────────────────────────────────

def find_entry(exp, by_exp, days_before_expiry=(3,2,4,1)):
    trades = by_exp[exp]
    available = [t for t in trades if t < exp]
    for offset in days_before_expiry:
        target = exp - timedelta(days=offset)
        if target in available: return target
    week_start = exp - timedelta(days=6)
    week_trades = [t for t in available if t >= week_start]
    return week_trades[0] if week_trades else None


# ── Single trade executor ──────────────────────────────────────────────────────

def execute_trade(file_idx, exp, entry_date, exit_date, right, strike_offset=0,
                  entry_min="09:15", exit_min="15:29"):
    entry_path = file_idx.get((exp, entry_date))
    exit_path  = file_idx.get((exp, exit_date))
    if entry_path is None or exit_path is None:
        return None

    spot_open, _ = load_nifty_spot(entry_date)
    if spot_open is None: return None

    atm = atm_strike(spot_open)
    strike = atm + strike_offset

    df_entry = load_chain(entry_path)
    df_exit  = load_chain(exit_path)

    entry_px = get_option_px(df_entry, strike, right, entry_min, col="open")
    if entry_px is None or entry_px <= 0:
        entry_px = get_option_px(df_entry, strike, right, entry_min, col="close")
    if entry_px is None or entry_px <= 0: return None

    exit_px = get_option_px(df_exit, strike, right, exit_min, col="close")
    if exit_px is None: exit_px = 0

    slip         = NIFTY_OTM_SLIPPAGE if strike_offset != 0 else NIFTY_ATM_SLIPPAGE
    slip_eff     = slip + LATENCY_BUFFER          # effective slippage per side
    pnl_gross    = (exit_px - entry_px) * LOT_SIZE
    fees         = calculate_total_cost(entry_px, exit_px, LOT_SIZE)
    slippage     = 2 * slip_eff * LOT_SIZE        # entry side + exit side
    pnl_net      = round(pnl_gross - fees - slippage, 2)
    pnl_per_unit = round(pnl_net / LOT_SIZE, 2)
    cost         = (entry_px + slip_eff) * LOT_SIZE + BROKERAGE_PER_ORDER

    return dict(
        exp=exp, entry_date=entry_date, exit_date=exit_date,
        right=right, strike=strike, offset=strike_offset,
        spot=round(spot_open, 2), atm=atm,
        entry_px=round(entry_px, 2), exit_px=round(exit_px, 2),
        pnl_per_unit=round(pnl_per_unit, 2),
        pnl_gross=round(pnl_gross, 2), pnl_net=round(pnl_net, 2),
        cost=round(cost, 2),
        pct_return=round(pnl_net/max(cost,1)*100, 1),
        won=(pnl_net > 0)
    )


# ── Run all strategies ────────────────────────────────────────────────────────

def run_all(file_idx, by_exp):
    expiries = sorted(k for k in by_exp if str(k)[:4] == "2024" and str(k) <= "2024-12-31")

    strategies = {
        "A: ATM Call (Mon→Thu)":     ("CE", 0,   False),
        "B: ATM Put  (Mon→Thu)":     ("PE", 0,   False),
        "C: ATM Straddle (Mon→Thu)": ("ST", 0,   False),
        "D: OTM Call +50 (Mon→Thu)": ("CE", +50, False),
        "E: OTM Put  -50 (Mon→Thu)": ("PE", -50, False),
        "F: ATM Call (Exp day)":     ("CE", 0,   True),
        "G: ATM Put  (Exp day)":     ("PE", 0,   True),
        "H: ATM Straddle (Exp day)": ("ST", 0,   True),
    }

    results = {s: [] for s in strategies}

    for exp in expiries:
        entry = find_entry(exp, by_exp)
        if entry is None: continue

        for strat_name, (right, offset, expiry_day) in strategies.items():
            entry_date = exp if expiry_day else entry
            exit_date  = exp

            if right == "ST":
                ce = execute_trade(file_idx, exp, entry_date, exit_date, "CE", 0)
                pe = execute_trade(file_idx, exp, entry_date, exit_date, "PE", 0)
                if ce and pe:
                    combined = dict(ce)
                    combined["entry_px"]      = round(ce["entry_px"] + pe["entry_px"], 2)
                    combined["exit_px"]       = round(ce["exit_px"]  + pe["exit_px"],  2)
                    combined["pnl_per_unit"]  = round(ce["pnl_per_unit"] + pe["pnl_per_unit"], 2)
                    combined["pnl_gross"]     = round(ce["pnl_gross"]    + pe["pnl_gross"], 2)
                    combined["pnl_net"]       = round(ce["pnl_net"]      + pe["pnl_net"] - 2*BROKERAGE_PER_ORDER, 2)
                    combined["cost"]          = round(ce["cost"]          + pe["cost"],    2)
                    combined["pct_return"]    = round(combined["pnl_net"] / max(combined["cost"],1)*100, 1)
                    combined["won"]           = combined["pnl_net"] > 0
                    combined["ce_px"]         = ce["entry_px"]
                    combined["pe_px"]         = pe["entry_px"]
                    results[strat_name].append(combined)
            else:
                t = execute_trade(file_idx, exp, entry_date, exit_date, right, offset)
                if t: results[strat_name].append(t)

    return results


# ── Stats ─────────────────────────────────────────────────────────────────────

def summarize(trades):
    if not trades: return {}
    pnls = [t["pnl_net"] for t in trades]
    wins = [p for p in pnls if p > 0]
    loss = [p for p in pnls if p <= 0]
    costs= [t["cost"] for t in trades]
    pcts = [t["pct_return"] for t in trades]
    return dict(
        n=len(trades),
        wins=len(wins), losses=len(loss),
        win_rate=round(len(wins)/len(trades)*100, 1),
        total_pnl=round(sum(pnls), 0),
        avg_pnl=round(np.mean(pnls), 0),
        avg_win=round(np.mean(wins), 0) if wins else 0,
        avg_loss=round(np.mean(loss), 0) if loss else 0,
        max_win=round(max(pnls), 0),
        max_loss=round(min(pnls), 0),
        avg_cost=round(np.mean(costs), 0),
        avg_return_pct=round(np.mean(pcts), 1),
        best_pct=round(max(pcts), 1),
        worst_pct=round(min(pcts), 1),
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(W)
    print("  NIFTY WEEKLY OPTIONS BUYING BACKTEST  --  Full Year 2024")
    print(f"  Lot size: {LOT_SIZE}  |  Brokerage: Rs {BROKERAGE_PER_ORDER}/order"
          f"  |  Slip: ATM {NIFTY_ATM_SLIPPAGE}+{LATENCY_BUFFER} / OTM {NIFTY_OTM_SLIPPAGE}+{LATENCY_BUFFER} pts/side")
    print(f"  Capital: Rs {INITIAL:,}  |  Positions: 1 lot per trade")
    print(W)

    print("\n  Building file index...")
    file_idx, by_exp = build_index()
    expiries_2024 = sorted(k for k in by_exp if str(k)[:4]=="2024" and str(k)<="2024-12-31")
    print(f"  Total files indexed: {len(file_idx)}")
    print(f"  2024 weekly expiries: {len(expiries_2024)}")
    print(f"  Running strategies...")

    results = run_all(file_idx, by_exp)
    print(f"  Done in {time.time()-t0:.1f}s\n")

    print(W); print("  MASTER SUMMARY  --  All Strategies"); print(W)
    print(f"\n  {'Strategy':<30} {'Trades':>7} {'WinRate':>8} {'TotalP&L':>11}"
          f" {'AvgP&L':>9} {'MaxWin':>9} {'MaxLoss':>9} {'AvgCost':>9}")
    print("  "+SEP)
    for strat, trades in results.items():
        s = summarize(trades)
        if not s: continue
        print(f"  {strat:<30} {s['n']:>7} {s['win_rate']:>7.1f}%"
              f" Rs{s['total_pnl']:>9,.0f}"
              f" Rs{s['avg_pnl']:>7,.0f}"
              f" Rs{s['max_win']:>7,.0f}"
              f" Rs{s['max_loss']:>7,.0f}"
              f" Rs{s['avg_cost']:>7,.0f}")

    print(f"\n{W}"); print("  CAPITAL GROWTH  --  Rs 1 lakh, 1 lot every week"); print(W)
    for strat, trades in results.items():
        s = summarize(trades)
        if not s: continue
        cap  = INITIAL + s["total_pnl"]
        cagr = (cap/INITIAL - 1) * 100
        print(f"  {strat:<30} Rs{INITIAL:>8,} → Rs{cap:>8,.0f}  ({cagr:>+.1f}%)")

    print(f"\n{W}"); print("  TRADE LOG  --  A: ATM Call (Mon->Thu)"); print(W)
    trades_a = results.get("A: ATM Call (Mon→Thu)", [])
    print(f"\n  {'#':<4} {'ExpDate':<12} {'Entry':<12} {'Nifty':>8} {'Strike':>8}"
          f" {'BuyPx':>8} {'SellPx':>8} {'P&L':>10} {'%Ret':>7} {'W/L':>5}")
    print("  "+SEP)
    cum = 0
    for i, t in enumerate(trades_a, 1):
        cum += t["pnl_net"]
        wl = "WIN" if t["won"] else "loss"
        print(f"  {i:<4} {str(t['exp']):<12} {str(t['entry_date']):<12}"
              f" {t['spot']:>8.0f} {t['strike']:>8}"
              f" {t['entry_px']:>8.1f} {t['exit_px']:>8.1f}"
              f" Rs{t['pnl_net']:>8,.0f} {t['pct_return']:>6.1f}% {wl:>5}")
    print(f"  CUMULATIVE: Rs{cum:,.0f}")

    print(f"\n  Runtime: {time.time()-t0:.1f}s\n")
    print(W)


if __name__ == "__main__":
    main()
