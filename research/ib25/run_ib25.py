"""The IB-25 retracement, taken apart. Research block only until the final section."""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ib25_core as M  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
POST = dict(retr=0.25, stop_frac=0.50, slope_win=20, slope_thr=0.0, max_cross=99)


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124)


def show(D, rows, names, blocks=("research",)):
    keys = ["n", "pct", "tot", "pf", "win", "dd", "pts", "R", "risk_med"]
    lab = {"n": "trades", "pct": "% of price / trade", "tot": "total %", "pf": "profit factor",
           "win": "win rate %", "dd": "max drawdown %", "pts": "points / trade",
           "R": "mean R (diagnostic)", "risk_med": "median risk (points)"}
    print(f"  {'metric':24s}" + "".join(f"{x:>17s}" for x in names))
    for k in keys:
        print(f"  {lab[k]:24s}" + "".join(
            f"{(r.get(k, float('nan'))):>17.4f}" if k not in ("n",) else f"{r.get(k,0):>17d}"
            for r in rows))


def blk(t, b):
    return t[t["block"] == b] if len(t) else t


if __name__ == "__main__":
    D = M.build("NQ")
    us = np.unique(D["sess"])
    line("THE RULE AS POSTED")
    print(f"  NQ 1-minute, {len(us):,} RTH sessions {us[0]} to {us[-1]}, split 65/35 at {D['cut']}")
    print(f"  VWAP anchored 09:30 · range 09:30 to min(now, 10:30) · first entry 10:21 · "
          f"cutoff 12:00 · sweep voids")
    print(f"  limit at 25% of the range from the target-side extreme · target that extreme · "
          f"stop at 50% · one order, one trade a session")
    print(f"  cost {D['cost']} points a side + {D['tick']} slippage; scored in PERCENT OF ENTRY "
          f"PRICE, R printed only as a diagnostic")
    t = M.run(D, **POST)
    show(D, [M.stats(blk(t, "research")), M.stats(blk(t, "locked"))],
         ["research", "locked (not read yet)"])
    print(f"\n  sessions producing a trade: {100*len(t)/len(us):.1f}%")
    print(f"  exit mix (research): "
          + "  ".join(f"{k} {100*v:.0f}%" for k, v in
                      blk(t, "research")["exit_reason"].value_counts(normalize=True).items()))

    line("A. THE RISK DENOMINATOR -- why this is scored in percent of price")
    r = t["risk"]
    print(f"  risk = (stop_frac - retr) x range = 0.25 x range")
    print(f"  quantiles (points): p1 {r.quantile(.01):.2f}  p5 {r.quantile(.05):.2f}  "
          f"p50 {r.median():.2f}  p95 {r.quantile(.95):.2f}  max {r.max():.2f}")
    q = pd.qcut(t["risk"], 5, labels=False)
    print(f"\n  {'risk quintile':16s}{'n':>6s}{'mean R':>10s}{'mean points':>14s}"
          f"{'mean % of price':>18s}")
    for i in range(5):
        g = t[q == i]
        print(f"  {i+1:<16d}{len(g):>6d}{g['R'].mean():>10.4f}{g['net_pts'].mean():>14.3f}"
              f"{g['pct'].mean():>18.4f}")
    print("  If R and points disagree in sign across quintiles, R is measuring the denominator.")

    line("B. THE RETRACEMENT LADDER -- is 25% the mechanism, or is it just depth?")
    print(f"  {'retr':>6s}{'n':>7s}{'% / trade':>12s}{'total %':>10s}{'PF':>8s}"
          f"{'win %':>8s}{'points':>10s}{'risk med':>10s}")
    for rr in (0.00, 0.10, 0.15, 0.25, 0.35, 0.50):
        q = dict(POST); q["retr"] = rr
        if rr >= q["stop_frac"]:
            q["stop_frac"] = rr + 0.25
        s = M.stats(blk(M.run(D, **q), "research"))
        print(f"  {rr:>6.2f}{s['n']:>7d}{s['pct']:>12.4f}{s['tot']:>10.2f}{s['pf']:>8.3f}"
              f"{s['win']:>8.1f}{s['pts']:>10.3f}{s['risk_med']:>10.1f}")
    print("  STUDY_V58 found this axis monotone on a DIFFERENT IB family -- deeper is better all")
    print("  the way to 0.50 -- because a retracement fraction IS a resting limit in range units.")

    line("C. THE STOP LADDER -- the post says 75% raises the win rate. Does it raise expectancy?")
    print(f"  {'stop':>6s}{'RR':>7s}{'n':>7s}{'% / trade':>12s}{'total %':>10s}{'PF':>8s}"
          f"{'win %':>8s}{'break-even win %':>18s}")
    for sf in (0.35, 0.50, 0.625, 0.75, 1.00):
        q = dict(POST); q["stop_frac"] = sf
        s = M.stats(blk(M.run(D, **q), "research"))
        rrr = 0.25 / (sf - 0.25)
        print(f"  {sf:>6.2f}{rrr:>7.2f}{s['n']:>7d}{s['pct']:>12.4f}{s['tot']:>10.2f}"
              f"{s['pf']:>8.3f}{s['win']:>8.1f}{100/(1+rrr):>18.1f}")
    print("  The last column is the driftless break-even. A win rate that rises exactly with the")
    print("  break-even is the barrier geometry, not an edge.")

    line("D. THE TWO JUDGEMENT CALLS -- do the VWAP slope and the chop ceiling earn anything?")
    print(f"  {'slope thr':>10s}{'max cross':>11s}{'n':>7s}{'% kept':>9s}{'% / trade':>12s}"
          f"{'PF':>8s}{'win %':>8s}")
    base_n = M.stats(blk(t, "research"))["n"]
    for thr in (0.0, 0.05, 0.10, 0.20):
        for mc in (99, 12, 8, 5):
            q = dict(POST); q["slope_thr"] = thr; q["max_cross"] = mc
            s = M.stats(blk(M.run(D, **q), "research"))
            if s["n"] < 25:
                continue
            print(f"  {thr:>10.2f}{mc:>11d}{s['n']:>7d}{100*s['n']/base_n:>8.0f}%"
                  f"{s['pct']:>12.4f}{s['pf']:>8.3f}{s['win']:>8.1f}")

    line("E. ABLATIONS -- what each remaining component is worth on the research block")
    abl = [("as posted", dict(POST)),
           ("no sweep veto", dict(POST, use_sweep=False)),
           ("no 12:00 cutoff (to 15:00)", dict(POST, cutoff=15 * 60)),
           ("longs only", dict(POST, allow_short=False)),
           ("shorts only", dict(POST, allow_long=False)),
           ("target 25% short of the extreme", dict(POST, tgt_frac=0.05)),
           ("slope window 5 min", dict(POST, slope_win=5)),
           ("slope window 60 min", dict(POST, slope_win=60))]
    print(f"  {'variant':34s}{'n':>7s}{'% / trade':>12s}{'total %':>10s}{'PF':>8s}{'win %':>8s}")
    for nm, q in abl:
        s = M.stats(blk(M.run(D, **q), "research"))
        print(f"  {nm:34s}{s['n']:>7d}{s['pct']:>12.4f}{s['tot']:>10.2f}{s['pf']:>8.3f}"
              f"{s['win']:>8.1f}")

    line("F. ZERO-COST -- is this an execution problem or is there no edge?")
    print(f"  {'variant':34s}{'net % / trade':>16s}{'GROSS % / trade':>18s}"
          f"{'cost as % of risk':>20s}")
    for nm, q in (("as posted", dict(POST)), ("retr 0.50 / stop 0.75", dict(POST, retr=0.50,
                                                                           stop_frac=0.75))):
        a = M.stats(blk(M.run(D, **q), "research"))
        b = M.stats(blk(M.run(D, cost=0.0, slip=0.0, **q), "research"))
        rt = 2 * (D["cost"] + D["tick"])
        print(f"  {nm:34s}{a['pct']:>16.4f}{b['pct']:>18.4f}"
              f"{100 * rt / a['risk_med']:>19.1f}%")
