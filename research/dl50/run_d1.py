"""The geometry and the base rates, before any model. This decides whether a model is worth fitting.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402


def main():
    f = D.load(15)
    print("IS 50 POINTS THE SAME TRADE ACROSS THE SAMPLE?  (US30 15m, median per year)")
    g = D.geometry(f)
    print(g.round(3).to_string())
    a, b = g["pct_of_price"].iloc[0], g["pct_of_price"].iloc[-1]
    c, d = g["in_atr"].iloc[0], g["in_atr"].iloc[-1]
    print(f"  as a share of PRICE the stop shrinks {a:.3f}% -> {b:.3f}%  ({a/b:.2f}x)")
    print(f"  in ATR units it moves {c:.2f} -> {d:.2f}  ({c/d:.2f}x)")

    print("\nWHAT EACH TARGET NEEDS, against a driftless price")
    print(f"{'target':>8}{'R':>6}{'driftless':>12}{'after cost':>12}{'cost gap':>10}")
    for t in D.TARGETS:
        lo, be = D.breakeven(t)
        print(f"{t:>8.0f}{t/D.STOP_PTS:>6.1f}{lo*100:>11.2f}%{be*100:>11.2f}%{(be-lo)*100:>9.2f}")
    print(f"  round turn {D.COST} pts = {100*D.COST/D.STOP_PTS:.2f}% of a {D.STOP_PTS:.0f}-point stop")

    print("\nBASE RATES -- Donchian 20 + EMA200 state, both sides, 15m, hold cap 96 bars (1 day)")
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    mod = f["mod"].to_numpy().astype(np.int64)
    sess = np.unique(f.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    print(f"{'target':>7}{'blk':<10}{'n':>6}{'win%':>8}{'need':>8}{'gap':>7}"
          f"{'pts/trade':>11}{'PF':>7}{'hold':>8}{'amb%':>7}{'time%':>7}")
    for t in D.TARGETS:
        eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, t, 96,
                                         D.COST, -1, -1, mod)
        ts = f.index[eb]
        _, be = D.breakeven(t)
        for bl, sel in (("research", np.asarray(ts < cut)), ("HOLDOUT", np.asarray(ts >= cut))):
            rr = r[sel]
            win = float((rr > 0).mean())
            print(f"{t:>7.0f}{bl:<10}{len(rr):>6}{win*100:>7.2f}%{be*100:>7.2f}%"
                  f"{(win-be)*100:>+7.2f}{rr.mean():>11.3f}{D.pf(rr):>7.3f}"
                  f"{np.median(hl[sel])*15:>7.0f}m{float(amb[sel].mean())*100:>6.1f}%"
                  f"{float((why[sel]==2).mean())*100:>6.1f}%")


if __name__ == "__main__":
    main()
