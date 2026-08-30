"""
backtest_mismatch.py  --  NIFTY 2024 Mismatch/Arbitrage Strategies
====================================================================
Three strategies that SELL overpriced options (collect premium) rather
than buy options. These exploit structural mispricings, not direction.

STRATEGY A: Short Strangle (Tuned for 90%+ Win Rate)
  - Sell OTM CE + OTM PE each Monday
  - Strike selected from weekly range distribution to give 90%+ win rate
  - Win when Nifty stays inside the range (collects theta decay)
  - "Mismatch": Options consistently priced for MORE volatility than realized

STRATEGY B: Put-Call Skew Harvest (Sell Expensive, Buy Cheap)
  - PEs are consistently ~8-12 pts overpriced vs CEs at same ATM strike
  - Sell ATM CE+PE spreads, buy 100-pt wings as protection (Iron Condor)
  - Collect the skew premium, profit as skew normalizes or options decay
  - "Mismatch": CE-PE should equal S-K but it doesn't — PE trades fat

STRATEGY C: Opening Spike Fade (Sell the Open, Buy 5min Later)
  - At 09:15, options open at extreme prices from pre-market imbalanced orders
  - By 09:20 the price normalizes — the spike is a microstructure artifact
  - Strategy: sell ATM CE when 09:15 open >> 09:15 close by >Rs8
  - "Mismatch": first-minute auction price != fair market value

Data: C:\\Users\\GIGA\\Documents\\nifty 2024 options data
Lot size: 25 | Brokerage: Rs 20/order | Slippage: Rs 1/unit
Capital: Rs 2,00,000 (2 lakh baseline per strategy)
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

DATA    = Path(r"C:\Users\GIGA\Documents\nifty 2024 options data")
NSPOT   = DATA / "2024Nifty"
MONTHS  = ["2024JAN","2024FEB","2024MAR","2024APR","2024MAY","2024JUN",
           "2024JUL","2024AUG","2024SEP","2024OCT","2024NOV","2024DEC"]

LOT     = 25
CAPITAL = 200_000
W       = "=" * 78
SEP     = "-" * 78


# ── Helpers ──────────────────────────────────────────────────────────────────

def parse_dt(s): return datetime.strptime(s, '%d%b%y').date()
def atm(spot, interval=50): return round(spot / interval) * interval

def build_index():
    idx = {}
    by_exp = defaultdict(list)
    for m in MONTHS:
        mdir = DATA / m
        if not mdir.exists(): continue
        for f in mdir.iterdir():
            if f.suffix != '.csv': continue
            parts = f.stem.split('-')
            if len(parts) < 3: continue
            try:
                exp = parse_dt(parts[1]); trd = parse_dt(parts[2])
                idx[(exp, trd)] = f
                by_exp[exp].append(trd)
            except: pass
    for exp in by_exp: by_exp[exp].sort()
    return idx, by_exp

def find_entry(exp, by_exp):
    available = [t for t in by_exp[exp] if t < exp]
    for offset in (3, 2, 4, 1):
        t = exp - timedelta(days=offset)
        if t in available: return t
    week_start = exp - timedelta(days=6)
    week_trades = [t for t in available if t >= week_start]
    return week_trades[0] if week_trades else None

def load_chain(path):
    return pd.read_csv(path, dtype={'datetime': str, 'right': str})

def spot_at(trade_date):
    mon = trade_date.strftime('%Y%b').upper()
    fn  = NSPOT / f"Nifty-{mon}.csv"
    if not fn.exists(): return None
    df  = pd.read_csv(fn, dtype={'datetime': str})
    date_str = str(trade_date)
    day = df[df.datetime.str.startswith(date_str)]
    if day.empty: return None
    return float(day.iloc[0]['open'])

def get_px(df, strike, right, minute, col='close'):
    row = df[(df.strike_price == strike) & (df.right == right) &
             (df.datetime == minute)]
    if row.empty: return None
    return float(row.iloc[0][col])

def net_pnl(actual_sell, actual_buy, n_orders, slip_pts_total):
    """
    actual_sell     : sum of all option prices at which we SOLD (per unit, across legs)
    actual_buy      : sum of all option prices at which we BOUGHT (per unit, across legs)
    n_orders        : total number of order executions (each leg × entry+exit)
    slip_pts_total  : total slippage in index points per unit across all orders
    """
    gross    = (actual_sell - actual_buy) * LOT
    fees     = calculate_total_cost(
        buy_price=actual_buy,
        sell_price=actual_sell,
        quantity=LOT,
        brokerage=BROKERAGE_PER_ORDER * (n_orders // 2),
    )
    slippage = slip_pts_total * LOT
    return round(gross - fees - slippage, 2)


# ── Weekly Nifty Range Analysis ───────────────────────────────────────────────

def analyze_weekly_range():
    weekly = []
    for m in MONTHS:
        fn = NSPOT / f"Nifty-{m}.csv"
        if not fn.exists(): continue
        df = pd.read_csv(fn, dtype={'datetime': str})
        df['date'] = df.datetime.str[:10]
        for date, grp in df.groupby('date'):
            weekly.append({
                'date': date,
                'open': float(grp.iloc[0]['open']),
                'high': grp['high'].max(),
                'low':  grp['low'].min(),
                'close': float(grp.iloc[-1]['close'])
            })
    daily = pd.DataFrame(weekly).sort_values('date').reset_index(drop=True)
    daily['dt'] = pd.to_datetime(daily.date)

    week_ranges = []
    for w, grp in daily.groupby([daily.dt.dt.year, daily.dt.dt.isocalendar().week]):
        if len(grp) < 3: continue
        entry_open = float(grp.iloc[0]['open'])
        move_pct   = abs(float(grp.iloc[-1]['close']) - entry_open) / entry_open * 100
        range_pct  = (grp.high.max() - grp.low.min()) / entry_open * 100
        week_ranges.append({'entry_open': entry_open, 'move_pct': move_pct, 'range_pct': range_pct})
    return pd.DataFrame(week_ranges)


# ── Strategy A: Short Strangle ────────────────────────────────────────────────

def run_strangle(file_idx, by_exp, expiries, otm_pts):
    trades = []
    for exp in expiries:
        entry = find_entry(exp, by_exp)
        if entry is None: continue
        entry_path = file_idx.get((exp, entry))
        exit_path  = file_idx.get((exp, exp))
        if not entry_path or not exit_path: continue
        s = spot_at(entry)
        if not s: continue
        atm_k = atm(s)
        ce_strike = atm_k + otm_pts
        pe_strike = atm_k - otm_pts
        df_entry = load_chain(entry_path)
        df_exit  = load_chain(exit_path)
        ce_sell = get_px(df_entry, ce_strike, 'CE', '09:30', 'open')
        pe_sell = get_px(df_entry, pe_strike, 'PE', '09:30', 'open')
        ce_buy  = get_px(df_exit,  ce_strike, 'CE', '15:29', 'close')
        pe_buy  = get_px(df_exit,  pe_strike, 'PE', '15:29', 'close')
        if None in [ce_sell, pe_sell]: continue
        ce_buy = ce_buy or 0; pe_buy = pe_buy or 0
        slip_total = 4 * (NIFTY_OTM_SLIPPAGE + LATENCY_BUFFER)
        pnl = net_pnl(ce_sell + pe_sell, ce_buy + pe_buy, n_orders=4, slip_pts_total=slip_total)
        trades.append({
            'exp': exp, 'entry': entry,
            'spot': round(s, 0), 'atm': atm_k,
            'ce_strike': ce_strike, 'pe_strike': pe_strike,
            'ce_sell': round(ce_sell, 2), 'pe_sell': round(pe_sell, 2),
            'ce_buy': round(ce_buy, 2), 'pe_buy': round(pe_buy, 2),
            'premium_collected': round(ce_sell + pe_sell, 2),
            'premium_paid': round(ce_buy + pe_buy, 2),
            'pnl': pnl, 'won': pnl > 0,
            'month': exp.strftime('%Y-%b')
        })
    return trades


# ── Strategy B: Iron Condor ────────────────────────────────────────────────────

def run_skew_harvest(file_idx, by_exp, expiries):
    trades = []
    for exp in expiries:
        entry = find_entry(exp, by_exp)
        if entry is None: continue
        entry_path = file_idx.get((exp, entry))
        exit_path  = file_idx.get((exp, exp))
        if not entry_path or not exit_path: continue
        s = spot_at(entry)
        if not s: continue
        atm_k = atm(s)
        df_entry = load_chain(entry_path)
        df_exit  = load_chain(exit_path)
        pe_atm_sell   = get_px(df_entry, atm_k,    'PE', '09:30', 'open')
        pe_wing_buy   = get_px(df_entry, atm_k-100,'PE', '09:30', 'open')
        pe_atm_close  = get_px(df_exit,  atm_k,    'PE', '15:29', 'close') or 0
        pe_wing_close = get_px(df_exit,  atm_k-100,'PE', '15:29', 'close') or 0
        ce_atm_sell   = get_px(df_entry, atm_k,    'CE', '09:30', 'open')
        ce_wing_buy   = get_px(df_entry, atm_k+100,'CE', '09:30', 'open')
        ce_atm_close  = get_px(df_exit,  atm_k,    'CE', '15:29', 'close') or 0
        ce_wing_close = get_px(df_exit,  atm_k+100,'CE', '15:29', 'close') or 0
        if any(v is None for v in [pe_atm_sell, pe_wing_buy, ce_atm_sell, ce_wing_buy]): continue
        entry_credit = (pe_atm_sell - pe_wing_buy) + (ce_atm_sell - ce_wing_buy)
        exit_debit   = (pe_atm_close - pe_wing_close) + (ce_atm_close - ce_wing_close)
        # actual sells: ATM legs at entry + wing legs at exit
        actual_sell = pe_atm_sell + ce_atm_sell + pe_wing_close + ce_wing_close
        # actual buys: wing legs at entry + ATM legs at exit
        actual_buy  = pe_wing_buy + ce_wing_buy + pe_atm_close + ce_atm_close
        # slippage: 4 ATM orders + 4 OTM wing orders, each with latency buffer
        slip_total = (4 * (NIFTY_ATM_SLIPPAGE + LATENCY_BUFFER)
                      + 4 * (NIFTY_OTM_SLIPPAGE + LATENCY_BUFFER))
        pnl = net_pnl(actual_sell, actual_buy, n_orders=8, slip_pts_total=slip_total)
        skew = (s - atm_k) - (ce_atm_sell - pe_atm_sell)
        trades.append({
            'exp': exp, 'entry': entry,
            'spot': round(s, 0), 'atm': atm_k,
            'pe_atm_sell': round(pe_atm_sell, 2),
            'ce_atm_sell': round(ce_atm_sell, 2),
            'entry_credit': round(entry_credit, 2),
            'exit_debit':   round(exit_debit, 2),
            'skew': round(skew, 2),
            'pnl': pnl, 'won': pnl > 0,
            'month': exp.strftime('%Y-%b')
        })
    return trades


# ── Strategy C: Opening Spike Fade (BUGGY original — kept for comparison) ────

def run_spike_fade(file_idx, by_exp, expiries, min_spike=8):
    """Original version — has 2 bugs: look-ahead bias + multi-expiry double count."""
    trades = []
    for exp in expiries:
        for trd in [t for t in by_exp[exp] if t <= exp]:
            path = file_idx.get((exp, trd))
            if not path: continue
            df = load_chain(path)
            t  = df[df.datetime == '09:15'].copy()
            if t.empty: continue
            spot_open = spot_at(trd)
            if not spot_open: continue
            atm_k = atm(spot_open)
            for right in ['CE', 'PE']:
                row = t[(t.strike_price == atm_k) & (t.right == right)]
                if row.empty: continue
                open_px  = float(row.iloc[0]['open'])
                close_px = float(row.iloc[0]['close'])
                if open_px <= 0.5: continue
                spike = open_px - close_px
                if spike > min_spike:
                    slip_total = 2 * (NIFTY_ATM_SLIPPAGE + LATENCY_BUFFER)
                    pnl = net_pnl(open_px, close_px, n_orders=2, slip_pts_total=slip_total)
                    trades.append({
                        'exp': exp, 'trd': trd,
                        'strike': atm_k, 'right': right,
                        'sell_at': round(open_px, 2),
                        'buy_at':  round(close_px, 2),
                        'spike':   round(spike, 2),
                        'pnl': pnl, 'won': pnl > 0,
                        'month': exp.strftime('%Y-%b')
                    })
    return trades


# ── Strategy C v2: Fixed Spike Fade ──────────────────────────────────────────

def run_spike_fade_v2(file_idx, by_exp, expiries, apply_filter=False, min_spike=8):
    """
    Fixed version — two bugs corrected:

    Fix 1 (multi-expiry): for every calendar day only the NEAREST active expiry
    is traded, not all simultaneous expiry chains. This is how a real trader
    would operate (most liquid, near-week contract).

    Fix 2 (look-ahead): when apply_filter=False every qualifying day is traded
    regardless of whether the 9:15 candle actually spiked. Losses are included.
    This is the only honest way to evaluate the strategy.

    When apply_filter=True the original min_spike threshold is re-applied for
    comparison, but it still benefits from the look-ahead flaw — use as upper
    bound only, not as realistic expectation.
    """
    # Build: trade_date -> nearest active expiry (Bug 2 fix)
    date_to_exp = {}
    for exp in expiries:
        for trd in by_exp.get(exp, []):
            if trd > exp:
                continue
            prev = date_to_exp.get(trd)
            if prev is None or exp < prev:
                date_to_exp[trd] = exp

    trades = []
    for trd in sorted(date_to_exp):
        exp  = date_to_exp[trd]
        path = file_idx.get((exp, trd))
        if not path:
            continue
        df = load_chain(path)
        t  = df[df.datetime == '09:15'].copy()
        if t.empty:
            continue
        spot_open = spot_at(trd)
        if not spot_open:
            continue
        atm_k = atm(spot_open)

        for right in ['CE', 'PE']:
            row = t[(t.strike_price == atm_k) & (t.right == right)]
            if row.empty:
                continue
            open_px  = float(row.iloc[0]['open'])
            close_px = float(row.iloc[0]['close'])
            if open_px <= 0.5:
                continue

            spike = open_px - close_px

            # Bug 2 fix: only filter when explicitly requested (look-ahead mode)
            if apply_filter and spike <= min_spike:
                continue

            slip_total = 2 * (NIFTY_ATM_SLIPPAGE + LATENCY_BUFFER)
            pnl = net_pnl(open_px, close_px, n_orders=2, slip_pts_total=slip_total)
            trades.append({
                'exp': exp, 'trd': trd,
                'strike': atm_k, 'right': right,
                'sell_at': round(open_px, 2),
                'buy_at':  round(close_px, 2),
                'spike':   round(spike, 2),
                'pnl': pnl, 'won': pnl > 0,
                'month': exp.strftime('%Y-%b')
            })
    return trades


# ── Summary ───────────────────────────────────────────────────────────────────

def summarize(trades, name):
    if not trades:
        print(f"  {name}: NO TRADES"); return {}
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    loss = [p for p in pnls if p <= 0]
    return dict(name=name, n=len(trades), wins=len(wins), losses=len(loss),
                win_rate=len(wins)/len(trades)*100,
                total=sum(pnls), avg=np.mean(pnls),
                avg_win=np.mean(wins) if wins else 0,
                avg_loss=np.mean(loss) if loss else 0,
                max_win=max(pnls), max_loss=min(pnls))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(W)
    print("  NIFTY 2024 -- MISMATCH / ARBITRAGE OPTION STRATEGIES")
    print("  Exploiting structural mispricings, NOT directional bets")
    print(W)

    print("\n  Building index...")
    file_idx, by_exp = build_index()
    expiries = sorted(k for k in by_exp if str(k)[:4] == '2024' and str(k) <= '2024-12-31')
    print(f"  2024 expiries: {len(expiries)}")

    # Weekly range calibration
    print("\n  Analyzing Nifty weekly range distribution...")
    wr = analyze_weekly_range()
    print(f"\n  Weekly Range Percentiles ({len(wr)} weeks):")
    for pct in [50, 75, 80, 85, 90, 95]:
        move = np.percentile(wr.move_pct, pct)
        rang = np.percentile(wr.range_pct, pct)
        flag = " ← 90% win target" if pct == 90 else ""
        print(f"    {pct}th %ile: move={move:.2f}%  range={rang:.2f}%{flag}")

    avg_spot = wr.entry_open.mean()
    pts_90   = round(np.percentile(wr.move_pct, 90) / 100 * avg_spot / 50) * 50
    print(f"\n  For 90%+ win rate need ~±{pts_90:.0f} pts OTM on avg spot {avg_spot:.0f}")

    # Strategy A
    print(f"\n{W}"); print(f"  STRATEGY A: SHORT STRANGLE"); print(W)
    print(f"\n  {'OTM':>8} {'Trades':>7} {'WinRate':>9} {'TotalP&L':>12} {'AvgPnL':>9} {'MaxLoss':>9}")
    print("  " + SEP)
    results_a = {}
    for otm_pts in [100, 150, 200, 250, 300, 350]:
        trades = run_strangle(file_idx, by_exp, expiries, otm_pts)
        s = summarize(trades, f"Strangle ±{otm_pts}")
        results_a[otm_pts] = (trades, s)
        if s:
            flag = " ◄ 90%+" if s['win_rate'] >= 90 else ""
            print(f"  ±{otm_pts:>5} pts {s['n']:>7} {s['win_rate']:>8.1f}%"
                  f" Rs{s['total']:>10,.0f} Rs{s['avg']:>7,.0f} Rs{s['max_loss']:>7,.0f}{flag}")

    # Detailed breakdown for best strangle
    best_otm = 100
    for o in sorted(results_a):
        _, s = results_a[o]
        if s and s.get('win_rate', 0) >= 90:
            best_otm = o; break

    best_trades, _ = results_a[best_otm]
    print(f"\n  Trade log (Short Strangle ±{best_otm}pts):")
    print(f"  {'#':<4} {'Expiry':<12} {'Spot':>8} {'CE':>8} {'PE':>8} {'Credit':>10} {'Paid':>10} {'P&L':>10} {'W/L'}")
    print("  " + SEP)
    for i, t in enumerate(best_trades, 1):
        wl = "WIN" if t['won'] else "loss"
        print(f"  {i:<4} {str(t['exp']):<12} {t['spot']:>8.0f}"
              f" {t['ce_sell']:>8.1f} {t['pe_sell']:>8.1f}"
              f" Rs{t['premium_collected']*25:>8,.0f}"
              f" Rs{t['premium_paid']*25:>8,.0f}"
              f" Rs{t['pnl']:>8,.0f}  {wl}")

    # Strategy B
    print(f"\n{W}"); print(f"  STRATEGY B: IRON CONDOR (SKEW HARVEST)"); print(W)
    skew_trades = run_skew_harvest(file_idx, by_exp, expiries)
    skew_s = summarize(skew_trades, "Iron Condor")
    if skew_s:
        print(f"\n  Trades: {skew_s['n']}  Win: {skew_s['win_rate']:.1f}%"
              f"  P&L: Rs{skew_s['total']:,.0f}"
              f"  Avg win: Rs{skew_s['avg_win']:,.0f}  Avg loss: Rs{skew_s['avg_loss']:,.0f}")

    # Strategy C — three versions: buggy original, fixed+filter, fixed+no-filter
    print(f"\n{W}"); print(f"  STRATEGY C: OPENING SPIKE FADE — BUG AUDIT"); print(W)

    print("\n  [V1] ORIGINAL (2 bugs: look-ahead filter + multi-expiry double count)")
    sp_v1      = run_spike_fade(file_idx, by_exp, expiries, min_spike=8)
    sp_v1_s    = summarize(sp_v1, "V1-Buggy")
    if sp_v1_s:
        print(f"       Trades={sp_v1_s['n']}  Win={sp_v1_s['win_rate']:.1f}%"
              f"  P&L=Rs{sp_v1_s['total']:,.0f}  Avg=Rs{sp_v1_s['avg']:,.0f}")

    print("\n  [V2] NEAREST-EXPIRY ONLY + look-ahead filter still on (upper bound)")
    sp_v2      = run_spike_fade_v2(file_idx, by_exp, expiries, apply_filter=True,  min_spike=8)
    sp_v2_s    = summarize(sp_v2, "V2-NearestFiltered")
    if sp_v2_s:
        print(f"       Trades={sp_v2_s['n']}  Win={sp_v2_s['win_rate']:.1f}%"
              f"  P&L=Rs{sp_v2_s['total']:,.0f}  Avg=Rs{sp_v2_s['avg']:,.0f}")

    print("\n  [V3] FULLY FIXED — nearest expiry + NO look-ahead (REALISTIC)")
    sp_v3      = run_spike_fade_v2(file_idx, by_exp, expiries, apply_filter=False)
    sp_v3_s    = summarize(sp_v3, "V3-Realistic")
    if sp_v3_s:
        print(f"       Trades={sp_v3_s['n']}  Win={sp_v3_s['win_rate']:.1f}%"
              f"  P&L=Rs{sp_v3_s['total']:,.0f}  Avg=Rs{sp_v3_s['avg']:,.0f}")
        print(f"       AvgWin=Rs{sp_v3_s['avg_win']:,.0f}"
              f"  AvgLoss=Rs{sp_v3_s['avg_loss']:,.0f}"
              f"  MaxWin=Rs{sp_v3_s['max_win']:,.0f}"
              f"  MaxLoss=Rs{sp_v3_s['max_loss']:,.0f}")

    print(f"\n  Monthly breakdown (V3 — realistic):")
    by_month = defaultdict(list)
    for t in sp_v3: by_month[t['month']].append(t)
    print(f"  {'Month':<12} {'Trades':>8} {'Wins':>6} {'WinRate':>8} {'P&L':>12} {'Avg':>9}")
    print("  " + SEP)
    for mon, mts in sorted(by_month.items()):
        w = sum(1 for t in mts if t['pnl'] > 0)
        print(f"  {mon:<12} {len(mts):>8} {w:>6} {w/len(mts)*100:>7.1f}%"
              f" Rs{sum(t['pnl'] for t in mts):>10,.0f}"
              f" Rs{sum(t['pnl'] for t in mts)/len(mts):>7,.0f}")

    print(f"\n  --- CAPITAL REQUIREMENTS ---")
    print(f"  Intraday SPAN margin (1 lot short NIFTY): ~Rs 45,000-65,000")
    print(f"  Exposure margin:                           ~Rs 10,000-15,000")
    print(f"  For 1 leg (CE only OR PE only):            ~Rs 55,000-80,000")
    print(f"  For both legs (CE + PE):                   ~Rs 1,10,000-1,60,000")
    print(f"  Recommended minimum capital (with buffer): Rs 1,50,000")

    spike_s = sp_v3_s  # use fixed version for final comparison

    # Final
    print(f"\n{W}"); print("  FINAL COMPARISON"); print(W)
    for otm_pts in [100, 200, 300]:
        if otm_pts not in results_a: continue
        _, s = results_a[otm_pts]
        if s:
            print(f"  Strangle ±{otm_pts}pts: Win={s['win_rate']:.1f}%  "
                  f"P&L=Rs{s['total']:,.0f}  Cap=Rs{CAPITAL+s['total']:,.0f}")
    if skew_s:
        print(f"  Iron Condor:         Win={skew_s['win_rate']:.1f}%  "
              f"P&L=Rs{skew_s['total']:,.0f}  Cap=Rs{CAPITAL+skew_s['total']:,.0f}")
    if spike_s:
        print(f"  Opening Spike Fade:  Win={spike_s['win_rate']:.1f}%  "
              f"P&L=Rs{spike_s['total']:,.0f}  Cap=Rs{CAPITAL+spike_s['total']:,.0f}")

    print(f"\n  Runtime: {time.time()-t0:.1f}s\n{W}")


if __name__ == '__main__':
    main()
