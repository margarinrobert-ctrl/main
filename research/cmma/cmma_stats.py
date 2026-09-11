"""Profit factor, win rate, timeframe and holding time for the CMMA strategy.

A NOTE ON WHAT A "TRADE" IS HERE, because it decides three of the four numbers. The signal is a
CONTINUOUS target in [-1, 1] -- `tanh` bounds it and the efficiency ratio scales it -- so the
strategy never places a discrete trade with an entry and an exit. It re-sizes a position every day
and holds it only inside the session. Three readings are therefore reported and kept apart:

  PER DAY      each session's P&L is one observation. This is the unit the Sharpe and the win rate
               in `STUDY_CMMA.md` use, and it is the honest unit for a continuously-sized system.
  PER STANCE   consecutive days on the same SIDE grouped into one directional position, which is
               what a discretionary reader means by "a trade". Its holding time is in days.
  EXPOSURE     the clock time the position is actually on risk: 08:00-15:45 New York, so 7h45m a
               day, flat overnight and at weekends.

Profit factor is gross-profit over gross-loss on whichever unit is named. It is NOT invariant to
that choice: grouping days into stances nets winning and losing days against each other inside a
stance, which raises the per-stance PF above the per-day PF whenever runs are persistent.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmma_core as C            # noqa: E402


def pf(x):
    g = x[x > 0].sum()
    l = -x[x <= 0].sum()
    return float(g / l) if l > 0 else np.inf


def stance_table(p):
    """Consecutive same-SIDE days grouped into one directional position."""
    side = np.sign(p["sig"])
    grp = (side != side.shift(1)).cumsum()
    g = p.groupby(grp)
    out = pd.DataFrame({
        "side": g["sig"].first().pipe(np.sign),
        "days": g.size(),
        "net": g["net"].sum(),
        "gross": g["gross"].sum(),
        "avg_size": g["sig"].apply(lambda s: s.abs().mean()),
    })
    return out[out["side"] != 0]


def block(name, p, session_hours):
    st = stance_table(p)
    d = p["net"]
    print(f"\n  {name}")
    print(f"    PER DAY      n {len(d):>5d}   PF {pf(d):>5.3f}   win {(d > 0).mean() * 100:>5.1f}%"
          f"   mean {d.mean():+.3f} pts   median {d.median():+.3f}")
    print(f"    PER STANCE   n {len(st):>5d}   PF {pf(st['net']):>5.3f}   "
          f"win {(st['net'] > 0).mean() * 100:>5.1f}%   mean {st['net'].mean():+.3f} pts   "
          f"median {st['net'].median():+.3f}")
    print(f"    HOLD         {st['days'].mean():.2f} trading days a stance "
          f"(median {st['days'].median():.0f}, max {st['days'].max():.0f})"
          f"  =  {st['days'].mean() * session_hours:.1f} exposure-hours")
    print(f"    EXPOSURE     {session_hours:.2f} h a day, flat overnight; mean |target| "
          f"{p['sig'].abs().mean():.3f} contracts, max {p['sig'].abs().max():.3f}")
    long_d = d[p["sig"] > 0]
    short_d = d[p["sig"] < 0]
    print(f"    BY SIDE      long  n {len(long_d):>5d}  PF {pf(long_d):>5.3f}  "
          f"win {(long_d > 0).mean() * 100:>5.1f}%   |   "
          f"short n {len(short_d):>5d}  PF {pf(short_d):>5.3f}  "
          f"win {(short_d > 0).mean() * 100:>5.1f}%")
    return st


def main():
    h0, m0 = (int(x) for x in C.SESSION[0].split(":"))
    h1, m1 = (int(x) for x in C.SESSION[1].split(":"))
    hours = (h1 * 60 + m1 - h0 * 60 - m0) / 60.0
    print("=" * 100)
    print("CMMA -- PROFIT FACTOR, WIN RATE, TIMEFRAME AND HOLDING TIME")
    print("=" * 100)
    print(f"  TIMEFRAME: signal computed on DAILY bars; executed on the intraday series inside")
    print(f"  {C.SESSION[0]}-{C.SESSION[1]} New York ({hours:.2f} hours), flat overnight.")
    print("  All figures NET of $1.44/round turn + 1 tick slippage a side.")
    for mk, tf in (("NQ", "1-minute"), ("US100L", "15-minute")):
        f = C.load_intraday(mk)
        d = C.daily_from_intraday(f)
        s = C.signal(d)
        p = C.session_pnl(f, s, mode="endpoints")
        cut = C.split_at(p.index)
        IS = p.index < cut
        print("\n" + "=" * 100)
        print(f"  {mk}  --  execution bars {tf}, {len(p):,} traded days, "
              f"{p.index[0].date()} .. {p.index[-1].date()}")
        print("=" * 100)
        block("FULL SAMPLE", p, hours)
        block("in-sample (first 70%)", p[IS], hours)
        block("HOLDOUT (last 30%)", p[~IS], hours)


if __name__ == "__main__":
    main()
