"""WHY the arm inverts. The geometry fix failed, so the cause is elsewhere -- decompose by year.

The ATR barrier was the hypothesis: a fixed 50-point stop is 4.23 ATR in 2016 and 1.10 in 2025, so
research and holdout were not the same strategy, and making the stop k x ATR should have shrunk the
inversion. IT DID NOT -- every ATR cell is research-positive and holdout-negative, and at 1.0 and
1.25 ATR the PF gap is WIDER than the point version's. So the inversion is decay or regime, and
this asks which by splitting the same arm year by year and asking whether the ADX direction that
wins flips at the same place.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402

M0, M1, HOLD, TGT_R = 420, 660, 96, 3.0


def by_year(ts, r, rr, extra=None):
    d = pd.DataFrame(dict(y=pd.DatetimeIndex(ts).year, r=r, R=rr))
    if extra is not None:
        d["g"] = extra
    g = d.groupby("y").agg(n=("r", "size"), pts=("r", "mean"), R=("R", "mean"),
                           pf=("r", lambda x: D.pf(x.to_numpy())))
    return g


def main():
    f = D.load(15)
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    at = f["atr"].to_numpy(); mod = f["mod"].to_numpy().astype(np.int64)
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    a14, _, _ = D.adx(f, 14)
    ones = np.ones(len(c), np.int64)

    print("THE ARM, YEAR BY YEAR (07:00-11:00 entries, no flatten)")
    print(f"{'':6}{'50/150 pts':>26}{'1.25 ATR / 3R':>26}{'2.0 ATR / 3R':>26}")
    print(f"{'year':<6}{'n':>7}{'pts':>9}{'PF':>10}{'n':>7}{'pts':>9}{'PF':>10}"
          f"{'n':>7}{'pts':>9}{'PF':>10}")
    tabs = {}
    eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, 150.0, HOLD,
                                     D.COST, M0, M1, mod, -1)
    tabs["pts"] = by_year(f.index[eb], r, r / D.STOP_PTS)
    for k in (1.25, 2.0):
        eb2, r2, rr2, sd2, hl2, w2, a2 = D.walk_atr(o, h, l, c, at, eh, el, ou, od, k, TGT_R,
                                                    HOLD, D.COST, M0, M1, mod, -1, ones)
        tabs[k] = by_year(f.index[eb2], r2, rr2)
    yrs = sorted(set(tabs["pts"].index) | set(tabs[1.25].index) | set(tabs[2.0].index))
    for y in yrs:
        row = f"{y:<6}"
        for key in ("pts", 1.25, 2.0):
            t = tabs[key]
            if y in t.index:
                row += f"{int(t.loc[y,'n']):>7}{t.loc[y,'pts']:>9.2f}{t.loc[y,'pf']:>10.3f}"
            else:
                row += f"{'-':>7}{'-':>9}{'-':>10}"
        print(row)

    print("\nWHICH ADX DIRECTION WINS, YEAR BY YEAR (1.5 ATR / 3R, mean R)")
    eb0, r0, rr0, sd0, _, _, _ = D.walk_atr(o, h, l, c, at, eh, el, ou, od, 1.5, TGT_R, HOLD,
                                            D.COST, M0, M1, mod, -1, ones)
    sig0 = eb0 - 1
    d = pd.DataFrame(dict(y=pd.DatetimeIndex(f.index[eb0]).year, R=rr0,
                          adx=a14[sig0]))
    print(f"{'year':<6}{'n':>6}{'all':>9}{'ADX<=20':>10}{'n<=20':>7}"
          f"{'ADX>=25':>10}{'n>=25':>7}{'winner':>10}")
    for y, gg in d.groupby("y"):
        lo = gg[gg.adx <= 20]["R"]
        hi = gg[gg.adx >= 25]["R"]
        if len(lo) < 15 or len(hi) < 15:
            continue
        w = "low" if lo.mean() > hi.mean() else "high"
        print(f"{y:<6}{len(gg):>6}{gg.R.mean():>9.4f}{lo.mean():>10.4f}{len(lo):>7}"
              f"{hi.mean():>10.4f}{len(hi):>7}{w:>10}")

    print("\nWHAT CHANGED IN THE MARKET, not in the rule")
    yr = pd.DataFrame(dict(y=f.index.year, atr=at, c=c,
                           adx=a14, rng=(h - l)))
    q = yr.groupby("y").agg(median_atr=("atr", "median"), median_adx=("adx", "median"),
                            atr_pct=("atr", lambda x: np.nan), px=("c", "median"))
    q["atr_pct"] = yr.groupby("y").apply(lambda g: 100 * g.atr.median() / g.c.median())
    q["share_adx_under20"] = yr.groupby("y").adx.apply(lambda x: float((x <= 20).mean()))
    print(q.round(3).to_string())


if __name__ == "__main__":
    main()
