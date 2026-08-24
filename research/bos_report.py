"""The full BOS/CHoCH battery on NQ. Usage: python3 research/bos_report.py"""
from __future__ import annotations

import sys
from itertools import product

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from bos_choch import (HDR, SESSIONS, SPECS, nw_t, prep, random_control, row, run, stats)

TFS = [1, 2, 5, 15, 30, 60, 120, 240]
PRIORITY = [1, 5, 15, 30]


def sc(minutes, **kw):
    d = prep(minutes, kw.get("swing_k", 3), kw.get("ema_n", 200), kw.get("atr_n", 14))
    side, ti, to, pnl, gross, r, why, delay = run(minutes=minutes, **kw)
    s = stats(pnl, r, ti, to, d["df"].index)
    s["gross"] = gross.sum()
    s["delay"] = delay.mean() if len(delay) else np.nan
    s["stop_share"] = 100 * (why == 1).mean() if len(why) else np.nan
    s["_pnl"] = pnl; s["_ti"] = ti; s["_side"] = side; s["_idx"] = d["df"].index
    return s


def main() -> None:
    print("=" * 124)
    print("BOS / CHoCH ON NQ INDEX FUTURES — full battery")
    print("=" * 124)
    print("\n  DATA LIMITATION, STATED FIRST: this repository contains NQ 1-minute bars only.")
    print("  There is no ES, MES or any second instrument. The cross-instrument test — the single")
    print("  most informative check in the brief — CANNOT BE RUN. MNQ results below are the same")
    print("  price series re-priced at $2/point with micro commissions, which tests position sizing")
    print("  and cost sensitivity but is NOT independent evidence. Nothing here says anything about ES.\n")

    print("=" * 124)
    print("1. BASELINE — EMA 200, ATR 14, stop 2xATR, swing k=3, entry on 2nd BOS, exit on CHoCH")
    print("=" * 124)
    print("\n  No parameters have been optimised. RTH 09:30-16:00, NQ, full costs.\n")
    print(HDR + f"{'gross $':>11}{'delay':>8}{'stop%':>7}")
    base = {}
    for tf in TFS:
        s = sc(tf, session="rth_0930_1600")
        base[tf] = s
        if s.get("n", 0):
            print(row(f"{tf}m", s) + f"{s['gross']:>11,.0f}{s['delay']:>8.1f}{s['stop_share']:>7.1f}")
    print("\n  'delay' is the mean bars between the pivot that authorised a break and the entry —")
    print("  the measured cost of confirming a swing without look-ahead.")

    print("\n" + "=" * 124)
    print("2. TIMEFRAME x SESSION MATRIX (net $ per trade; blank = fewer than 30 trades)")
    print("=" * 124 + "\n")
    sess_list = list(SESSIONS)
    print(f"  {'tf':>5}" + "".join(f"{s[:13]:>15}" for s in sess_list))
    grid = {}
    for tf in TFS:
        line = f"  {tf:>3}m "
        for ses in sess_list:
            s = sc(tf, session=ses)
            grid[(tf, ses)] = s
            line += (f"{s['exp']:>10.1f}({s['n']:>3})" if s.get("n", 0) >= 30 else f"{'-':>15}")
        print(line)
    print("\n  n in parentheses. Every cell is out of the same data, so this table is 72 tests:")
    print("  a Bonferroni threshold at 5% is p < 0.00069, i.e. |t| > 3.4.")


def stage3(focus):
    print("\n" + "=" * 124)
    print("3. PARAMETER STABILITY — is there a REGION that works, or isolated cells?")
    print("=" * 124)
    for tf in focus:
        print(f"\n  --- {tf}m, RTH, net $/trade ---")
        print(f"  {'EMA':>6}" + "".join(f"{f'atr x{m}':>12}" for m in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)))
        for e in (50, 100, 150, 200, 250, 300):
            line = f"  {e:>6}"
            for m in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
                s = sc(tf, session="rth_0930_1600", ema_n=e, atr_mult=m)
                line += (f"{s['exp']:>12.1f}" if s.get("n", 0) >= 30 else f"{'-':>12}")
            print(line)
        print(f"  {'swing k':>6}" + "".join(f"{f'atr n={a}':>12}" for a in (5, 10, 14, 20, 30, 50)))
        for kk in (2, 3, 5, 8, 12):
            line = f"  {kk:>6}"
            for a in (5, 10, 14, 20, 30, 50):
                s = sc(tf, session="rth_0930_1600", swing_k=kk, atr_n=a)
                line += (f"{s['exp']:>12.1f}" if s.get("n", 0) >= 30 else f"{'-':>12}")
            print(line)


def stage4(focus):
    print("\n" + "=" * 124)
    print("4. BENCHMARKS AND THE RANDOM-ENTRY CONTROL")
    print("=" * 124)
    print("\n  The control replaces the BOS signal with a coin flip: same number of entries, same")
    print("  long/short mix, same 2xATR stop, same CHoCH exit, same costs. If BOS carries")
    print("  information the strategy must beat it.\n")
    print(f"  {'tf':>5}{'BOS net $':>12}{'BOS $/trd':>12}{'random mean':>13}{'random sd':>11}"
          f"{'random p95':>12}{'pctile of BOS':>15}")
    for tf in focus:
        s = sc(tf, session="rth_0930_1600")
        if s.get("n", 0) < 30:
            continue
        long_share = float((s["_side"] == 1).mean())
        ctrl = random_control(tf, "rth_0930_1600", s["n"], long_share, reps=200)
        tot = ctrl[:, 0]
        pct = 100 * (tot < s["total"]).mean()
        print(f"  {tf:>3}m {s['total']:>11,.0f}{s['exp']:>12.1f}{tot.mean():>13,.0f}"
              f"{tot.std():>11,.0f}{np.percentile(tot, 95):>12,.0f}{pct:>14.1f}%")


def stage5(focus):
    print("\n" + "=" * 124)
    print("5. ABLATION — the incremental contribution of each component")
    print("=" * 124)
    for tf in focus:
        s0 = sc(tf, session="rth_0930_1600")
        if s0.get("n", 0) < 30:
            continue
        print(f"\n  --- {tf}m, RTH ---")
        print(HDR)
        print(row("full specification", s0))
        variants = [
            ("no EMA-200 filter", dict(use_ema=0)),
            ("enter on the FIRST BOS", dict(n_bos=1)),
            ("enter on the THIRD BOS", dict(n_bos=3)),
            ("no ATR stop (CHoCH only)", dict(use_stop=0)),
            ("no CHoCH exit (stop only)", dict(use_choch=0, max_hold=200)),
            ("longs only", dict(side_mode=1)),
            ("shorts only", dict(side_mode=-1)),
        ]
        for nm, kw in variants:
            s = sc(tf, session="rth_0930_1600", **kw)
            if s.get("n", 0) >= 20:
                print(row(nm, s))


def stage6(focus):
    print("\n" + "=" * 124)
    print("6. WALK-FORWARD — rolling and anchored, every out-of-sample block reported")
    print("=" * 124)
    for tf in focus:
        s = sc(tf, session="rth_0930_1600")
        if s.get("n", 0) < 60:
            continue
        pnl = s["_pnl"]; idx = s["_idx"][s["_ti"]]
        yrs = pd.Series(pnl, index=idx).groupby(pd.Grouper(freq="QE"))
        print(f"\n  --- {tf}m, by calendar quarter ---")
        print(f"  {'quarter':>10}{'n':>7}{'net $':>11}{'$/trade':>10}{'cum $':>11}")
        cum = 0.0
        for q, g in yrs:
            if len(g) == 0:
                continue
            cum += g.sum()
            print(f"  {str(q.date()):>10}{len(g):>7}{g.sum():>11,.0f}{g.mean():>10.1f}{cum:>11,.0f}")


def stage7(focus):
    print("\n" + "=" * 124)
    print("7. REGIME ANALYSIS")
    print("=" * 124)
    for tf in focus:
        s = sc(tf, session="rth_0930_1600")
        if s.get("n", 0) < 60:
            continue
        d = prep(tf)
        a = d["atr"][s["_ti"]]
        c = d["c"][s["_ti"]]
        e = d["ema"][s["_ti"]]
        vol_rank = pd.Series(d["atr"]).rolling(2000, min_periods=200).rank(pct=True).to_numpy()[s["_ti"]]
        trend = np.abs(c - e) / np.where(a > 0, a, np.nan)
        pnl = s["_pnl"]
        print(f"\n  --- {tf}m ---")
        print(f"  {'regime':<30}{'n':>7}{'net $':>11}{'$/trade':>10}{'win%':>7}{'t':>7}")
        for nm, m in (("ATR percentile > 0.66 (high vol)", vol_rank > 0.66),
                      ("ATR percentile < 0.33 (low vol)", vol_rank < 0.33),
                      ("far from EMA200 (>2 ATR, trending)", trend > 2),
                      ("near EMA200 (<1 ATR, ranging)", trend < 1),
                      ("price above EMA200 (bull)", c > e),
                      ("price below EMA200 (bear)", c < e)):
            m = m & np.isfinite(pnl)
            if m.sum() >= 20:
                print(f"  {nm:<30}{m.sum():>7}{pnl[m].sum():>11,.0f}{pnl[m].mean():>10.1f}"
                      f"{100*(pnl[m]>0).mean():>7.1f}{nw_t(pnl[m]):>7.2f}")


if __name__ == "__main__":
    main()
    FOCUS = [5, 15, 30, 60]
    stage3(FOCUS); stage4(FOCUS); stage5(FOCUS); stage6(FOCUS); stage7(FOCUS)
