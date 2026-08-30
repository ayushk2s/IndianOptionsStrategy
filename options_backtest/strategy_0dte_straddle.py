"""
strategy_0dte_straddle.py  --  0DTE Short Straddle on Expiry Days
=================================================================
NIFTY (Thursday) + BANKNIFTY (Thursday 2020-2023, Wednesday 2024)
5-year backtest: 2020 - Oct 2024

Strategy logic (ZERO look-ahead bias):
  Entry  : Every expiry day at 09:30 OPEN — sell ATM CE + ATM PE
  Stop   : If either leg closes a 1-min bar at >= 2x its entry price, exit both
  Exit   : 15:15 CLOSE (time-based)
  ATM    : round(spot_at_09:30 / interval) x interval
           Nifty interval = 50, BankNifty interval = 100

Lot sizes used:
  NIFTY      : 50 units (2020 - Jun 2024), 25 units (Jul 2024+)
  BANKNIFTY  : 15 units throughout 2020-2024

Data path: C:\\Users\\GIGA\\Documents\\nifty 2024 options data
"""

import re, sys, time
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from fees_config import (
    calculate_total_cost, BROKERAGE_PER_ORDER,
    NIFTY_ATM_SLIPPAGE, LATENCY_BUFFER,
)

BASE  = Path(r"C:\Users\GIGA\Documents\nifty 2024 options data")
W     = "=" * 80
SEP   = "-" * 80
STOP_MULT      = 2.0   # per-leg stop: exit both when either leg reaches 2x entry price
USE_IC         = False  # naked straddle — IC adds too many legs/fees for 0DTE edge

# ── Lot size helpers ──────────────────────────────────────────────────────────

NIFTY_LOT_CUT  = date(2024, 7, 19)   # lot changed from 50 → 25

def nifty_lot(trd: date) -> int:
    return 25 if trd >= NIFTY_LOT_CUT else 50

def bn_lot(_trd: date) -> int:
    return 15   # stable throughout 2020-2024

# ── File helpers ──────────────────────────────────────────────────────────────

def parse_file_date(fname: str) -> date | None:
    """Extract trading date from filename like nifty_options_04_01_2024.csv"""
    m = re.search(r'(\d{2})_(\d{2})_(\d{4})', fname)
    if not m:
        return None
    day, mon, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(yr, mon, day)
    except ValueError:
        return None

def parse_expiry_from_df(df: pd.DataFrame, prefix: str) -> date | None:
    """Parse expiry date from first symbol in dataframe."""
    sym = df['symbol'].iloc[0] if not df.empty else ''
    m = re.match(rf'{prefix}(\d{{2}})(\w{{3}})(\d{{2}})', sym)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2) + m.group(3), '%d%b%y').date()
    except ValueError:
        return None

def atm_strike(spot: float, interval: int) -> int:
    return round(spot / interval) * interval

# ── Per-trade cost ────────────────────────────────────────────────────────────

def trade_cost(sell_px: float, buy_px: float, lot: int) -> float:
    """Full all-in cost for 1 short straddle leg pair (4 orders total)."""
    return calculate_total_cost(
        buy_price=buy_px,
        sell_price=sell_px,
        quantity=lot,
        brokerage=BROKERAGE_PER_ORDER * 2,   # 4 orders → n_orders//2 = 2
    )

def straddle_pnl(ce_sell, pe_sell, ce_buy, pe_buy, lot, slip_per_side):
    gross    = (ce_sell + pe_sell - ce_buy - pe_buy) * lot
    fees     = trade_cost(ce_sell + pe_sell, ce_buy + pe_buy, lot)
    slippage = 4 * (slip_per_side + LATENCY_BUFFER) * lot
    return round(gross - fees - slippage, 2)

# ── Core: run one instrument/year ────────────────────────────────────────────

def run_instrument(name: str, prefix: str, opt_dir: Path, spot_dir: Path,
                   lot_fn, atm_interval: int, slip: float, years: list[int]):
    trades = []

    for yr in years:
        for mo in range(1, 13):
            opt_mo  = opt_dir  / str(yr) / str(mo)
            spot_mo = spot_dir / str(yr) / str(mo)
            if not opt_mo.exists():
                continue

            for opt_file in sorted(opt_mo.glob('*.csv')):
                trd = parse_file_date(opt_file.name)
                if trd is None:
                    continue

                # quick check: read 2 rows to get expiry date
                try:
                    df_head = pd.read_csv(opt_file, nrows=3)
                except Exception:
                    continue
                exp = parse_expiry_from_df(df_head, prefix)
                if exp is None or exp != trd:
                    continue   # not expiry day

                # --- it IS expiry day ---

                # load spot file
                spot_fname_pat = f'{name.lower()}_spot{trd.strftime("%d_%m_%Y")}.csv'
                spot_file = spot_mo / spot_fname_pat
                if not spot_file.exists():
                    continue
                try:
                    df_spot = pd.read_csv(spot_file, dtype={'time': str})
                except Exception:
                    continue

                # Use 09:15 close as "settled open" for ATM calculation
                # Enter at 09:30 OPEN (15 min into session — more stable fills)
                row_915 = df_spot[df_spot['time'] == '09:15:00']
                row_930 = df_spot[df_spot['time'] == '09:30:00']
                if row_915.empty or row_930.empty:
                    continue
                spot_915_close = float(row_915.iloc[0]['close'])
                spot_open      = float(row_930.iloc[0]['open'])
                atm = atm_strike(spot_open, atm_interval)

                ce_sym = f'{prefix}{trd.strftime("%d%b%y").upper()}{atm}CE'
                pe_sym = f'{prefix}{trd.strftime("%d%b%y").upper()}{atm}PE'

                # load full options file, keep only our 2 symbols
                try:
                    df_opts = pd.read_csv(opt_file, dtype={'time': str})
                except Exception:
                    continue

                df_ce = df_opts[df_opts['symbol'] == ce_sym].set_index('time')
                df_pe = df_opts[df_opts['symbol'] == pe_sym].set_index('time')

                if df_ce.empty or df_pe.empty:
                    continue

                # entry at 09:30
                if '09:30:00' not in df_ce.index or '09:30:00' not in df_pe.index:
                    continue
                ce_entry = float(df_ce.loc['09:30:00', 'open'])
                pe_entry = float(df_pe.loc['09:30:00', 'open'])

                # Minimum liquidity filter
                straddle_credit = ce_entry + pe_entry
                if straddle_credit < 20:
                    continue

                net_credit = straddle_credit
                if ce_entry <= 0 or pe_entry <= 0:
                    continue

                ce_stop = ce_entry * STOP_MULT  # per-leg stop: exit fast on gamma explosion
                pe_stop = pe_entry * STOP_MULT

                # walk minutes 09:31 to 15:15 for straddle-total stop
                ce_exit = pe_exit = None
                exit_time = exit_reason = None

                all_times = sorted(set(df_ce.index) | set(df_pe.index))
                monitor_times = [
                    t for t in all_times
                    if '09:31:00' <= t <= '15:14:00'
                ]

                for t in monitor_times:
                    ce_now = float(df_ce.loc[t, 'close']) if t in df_ce.index else None
                    pe_now = float(df_pe.loc[t, 'close']) if t in df_pe.index else None
                    if ce_now is None or pe_now is None:
                        continue

                    # per-leg 2x stop: exit both when either leg reaches 2x entry price
                    # on expiry day, high gamma means a runaway leg won't recover
                    if ce_now >= ce_stop or pe_now >= pe_stop:
                        ce_exit     = ce_now
                        pe_exit     = pe_now
                        exit_time   = t
                        exit_reason = 'stop'
                        break

                # time exit at 15:15
                if ce_exit is None:
                    t = '15:15:00'
                    ce_exit = float(df_ce.loc[t, 'close']) if t in df_ce.index else 0.05
                    pe_exit = float(df_pe.loc[t, 'close']) if t in df_pe.index else 0.05
                    exit_time   = t
                    exit_reason = 'time'

                lot = lot_fn(trd)
                pnl = straddle_pnl(ce_entry, pe_entry, ce_exit, pe_exit, lot, slip)

                trades.append(dict(
                    date=trd, year=yr, expiry=exp,
                    spot=round(spot_open, 0), atm=atm, lot=lot,
                    ce_entry=round(ce_entry, 2), pe_entry=round(pe_entry, 2),
                    ce_exit=round(ce_exit, 2),   pe_exit=round(pe_exit, 2),
                    credit=round(straddle_credit, 2),
                    exit_reason=exit_reason, exit_time=exit_time,
                    pnl=pnl, won=(pnl > 0),
                ))

    return trades

# ── Summary helpers ───────────────────────────────────────────────────────────

def summarize(trades: list) -> dict:
    if not trades:
        return {}
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    loss = [p for p in pnls if p <= 0]
    stops = sum(1 for t in trades if t['exit_reason'] == 'stop')
    return dict(
        n=len(trades), wins=len(wins), losses=len(loss),
        win_rate=round(len(wins) / len(trades) * 100, 1),
        stop_rate=round(stops / len(trades) * 100, 1),
        total=round(sum(pnls), 0),
        avg=round(np.mean(pnls), 0),
        avg_win=round(np.mean(wins), 0) if wins else 0,
        avg_loss=round(np.mean(loss), 0) if loss else 0,
        max_win=round(max(pnls), 0),
        max_loss=round(min(pnls), 0),
    )

def print_year_table(trades: list, instrument: str):
    by_year = defaultdict(list)
    for t in trades:
        by_year[t['year']].append(t)

    print(f"\n  {'Year':<6} {'Exp':>5} {'Win%':>7} {'Stop%':>7} "
          f"{'TotalP&L':>12} {'AvgP&L':>9} {'MaxLoss':>10} {'CAGR':>8}")
    print("  " + SEP)

    initial = 200_000
    for yr in sorted(by_year):
        ts = by_year[yr]
        s  = summarize(ts)
        if not s:
            continue
        cagr = s['total'] / initial * 100
        print(f"  {yr:<6} {s['n']:>5} {s['win_rate']:>6.1f}% {s['stop_rate']:>6.1f}%"
              f" Rs{s['total']:>10,.0f} Rs{s['avg']:>7,.0f}"
              f" Rs{s['max_loss']:>8,.0f} {cagr:>+7.1f}%")

    print("  " + SEP)
    s_all = summarize(trades)
    years_covered = (max(by_year) - min(by_year) + 1)
    avg_annual = s_all['total'] / years_covered if years_covered else 0
    print(f"  {'ALL':<6} {s_all['n']:>5} {s_all['win_rate']:>6.1f}% {s_all['stop_rate']:>6.1f}%"
          f" Rs{s_all['total']:>10,.0f} Rs{s_all['avg']:>7,.0f}"
          f" Rs{s_all['max_loss']:>8,.0f}"
          f"  avg Rs{avg_annual:,.0f}/yr")

def print_monthly_heatmap(trades: list):
    """Show P&L grid: years as columns, months as rows."""
    by_ym = defaultdict(lambda: defaultdict(list))
    for t in trades:
        by_ym[t['date'].month][t['year']].append(t['pnl'])

    years = sorted(set(t['year'] for t in trades))
    print(f"\n  {'Month':<6}", end='')
    for yr in years:
        print(f"  {yr:>10}", end='')
    print()
    print("  " + SEP)

    month_names = ['Jan','Feb','Mar','Apr','May','Jun',
                   'Jul','Aug','Sep','Oct','Nov','Dec']
    for mo in range(1, 13):
        print(f"  {month_names[mo-1]:<6}", end='')
        for yr in years:
            pnls = by_ym[mo][yr]
            val  = sum(pnls) if pnls else None
            if val is None:
                print(f"  {'---':>10}", end='')
            else:
                print(f"  Rs{val:>7,.0f}", end='')
        print()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(W)
    print("  0DTE SHORT STRADDLE  --  NIFTY + BANKNIFTY  --  2020-2024")
    print(f"  Entry: 09:30 OPEN on expiry day  |  Exit: 15:15 or {STOP_MULT}x per-leg stop")
    print("  NO look-ahead bias  |  Full fee model  |  Realistic slippage")
    print(W)

    years = [2020, 2021, 2022, 2023, 2024]

    # ── NIFTY ────────────────────────────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  NIFTY  (Thursday weekly expiry, lot=50 pre Jul-2024, 25 after)")
    print(f"{'─'*80}")

    nifty_trades = run_instrument(
        name        = 'nifty',
        prefix      = 'NIFTY',
        opt_dir     = BASE / 'nifty_data'     / 'nifty_options',
        spot_dir    = BASE / 'nifty_data'     / 'nifty_spot',
        lot_fn      = nifty_lot,
        atm_interval= 50,
        slip        = NIFTY_ATM_SLIPPAGE,
        years       = years,
    )

    print_year_table(nifty_trades, 'NIFTY')
    print_monthly_heatmap(nifty_trades)

    ns = summarize(nifty_trades)
    if ns:
        stops = [t for t in nifty_trades if t['exit_reason']=='stop']
        print(f"\n  Stop-loss trades  : {len(stops)} / {ns['n']}")
        print(f"  Avg Win           : Rs {ns['avg_win']:,.0f}")
        print(f"  Avg Loss          : Rs {ns['avg_loss']:,.0f}")
        print(f"  Reward/Risk ratio : {abs(ns['avg_win']/ns['avg_loss']):.2f}")

    # ── BANKNIFTY ────────────────────────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  BANKNIFTY  (Thursday 2020-2023 | Wednesday 2024, lot=15 throughout)")
    print(f"{'─'*80}")

    bn_trades = run_instrument(
        name        = 'banknifty',
        prefix      = 'BANKNIFTY',
        opt_dir     = BASE / 'banknifty_data' / 'banknifty_options',
        spot_dir    = BASE / 'banknifty_data' / 'banknifty_spot',
        lot_fn      = bn_lot,
        atm_interval= 100,
        slip        = 3.0,    # BankNifty wider spreads
        years       = years,
    )

    print_year_table(bn_trades, 'BANKNIFTY')
    print_monthly_heatmap(bn_trades)

    bs = summarize(bn_trades)
    if bs:
        stops = [t for t in bn_trades if t['exit_reason']=='stop']
        print(f"\n  Stop-loss trades  : {len(stops)} / {bs['n']}")
        print(f"  Avg Win           : Rs {bs['avg_win']:,.0f}")
        print(f"  Avg Loss          : Rs {bs['avg_loss']:,.0f}")
        print(f"  Reward/Risk ratio : {abs(bs['avg_win']/bs['avg_loss']):.2f}")

    # ── Combined ─────────────────────────────────────────────────────────────
    print(f"\n{W}")
    print("  COMBINED SUMMARY  (Nifty + BankNifty, Rs 2L per strategy)")
    print(W)

    all_pnls  = [t['pnl'] for t in nifty_trades + bn_trades]
    combined  = sum(all_pnls)
    years_n   = (max(t['year'] for t in nifty_trades + bn_trades)
                 - min(t['year'] for t in nifty_trades + bn_trades) + 1)
    avg_ann   = combined / years_n

    if ns:
        print(f"  NIFTY 5yr P&L     : Rs {ns['total']:,.0f}"
              f"  ({ns['win_rate']:.1f}% win, Rs {ns['total']/years_n:,.0f}/yr avg)")
    if bs:
        print(f"  BANKNIFTY 5yr P&L : Rs {bs['total']:,.0f}"
              f"  ({bs['win_rate']:.1f}% win, Rs {bs['total']/years_n:,.0f}/yr avg)")
    print(f"  COMBINED 5yr P&L  : Rs {combined:,.0f}  (avg Rs {avg_ann:,.0f}/yr)")
    print(f"\n  Capital growth (Rs 2L per strategy = Rs 4L total):")
    print(f"    Start: Rs 4,00,000  →  End: Rs {400000+combined:,.0f}")
    print(f"    5yr Return: {combined/400000*100:.1f}%")
    print(f"    Annualised: {(combined/400000*100)/years_n:.1f}% per year")

    print(f"\n  Runtime: {time.time()-t0:.1f}s")
    print(W)


if __name__ == '__main__':
    main()
