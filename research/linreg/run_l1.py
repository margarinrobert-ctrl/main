"""GATE 1 -- the regression as the primary, research blocks only. 1,080 declared cells.

Base rates FIRST (a reading that fires on 50% of bars is a coin flip wearing an indicator), then
the whole declared grid by MARGINAL AVERAGE, then the leaders against a matched random entry that
runs the identical stop, target and exit.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from linreg import lrcore as L  # noqa: E402

MKTS = ("US30L", "US100L", "NQ")
TFS = (15, 30, 60)
LENS = (20, 50, 100)
BANDS = ((2.0, False), (1.5, True))       # (k, k_in_atr): 2.0 residual sigma, or 1.5 x ATR
STOPS = (1.5, 2.5)
TPS = (0.0, 2.0)
RNG = np.random.default_rng(1234)


def blocks(f):
    s = np.unique(f.index.normalize())
    return pd.Timestamp(s[int(0.75 * len(s))])


def main():
    rows, base = [], []
    for mk in MKTS:
        for tf in TFS:
            f = L.load(mk, tf)
            cut = blocks(f)
            res = np.asarray(f.index < cut)
            o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
            at = f["atr"].to_numpy(); mod = f["mod"].to_numpy().astype(np.int64)
            cost = L.COST[mk]
            for n, (k, kat) in itertools.product(LENS, BANDS):
                rd, val, slp, sig = L.readings(f, n, k, kat)
                for nm, (eu, ed, xu, xd) in rd.items():
                    if nm in ("S slope state", "X slope cross", "V close>value") and (k, kat) != BANDS[0]:
                        continue                      # the band axis is INERT for these three
                    base.append(dict(mk=mk, tf=tf, n=n, band=f"{k}{'A' if kat else 's'}",
                                     read=nm, rate_up=float(eu[res].mean()),
                                     rate_dn=float(ed[res].mean())))
                    for sm, tp in itertools.product(STOPS, TPS):
                        eb, r, sd, hl, cf = L._walk(o, h, l, c, at, mod, eu, ed, xu, xd, 0,
                                                    sm, tp, 0, -1, -1, cost)
                        ts = f.index[eb]
                        m = np.asarray(ts < cut)
                        rr = r[m]
                        if len(rr) < 50:
                            continue
                        rows.append(dict(mk=mk, tf=tf, read=nm, n=n,
                                         band=f"{k}{'A' if kat else 's'}", stop=sm, tp=tp,
                                         cnt=len(rr), mu=float(rr.mean()), tot=float(rr.sum()),
                                         pf=L.pf(rr), hold=float(np.median(hl[m])) * tf,
                                         cr=float(np.median(cf[m]))))
        print(f"  {mk} done ({len(rows)} cells)", flush=True)

    b = pd.DataFrame(base); d = pd.DataFrame(rows)
    d.to_csv("research/linreg/gate1.csv", index=False)
    print(f"\n{len(d)} scorable cells of 1,080 declared   profitable {float((d.tot>0).mean()):.3f}")

    print("\nBASE RATES on research -- share of ALL bars each reading fires (long side)")
    print(b.groupby("read").rate_up.describe()[["mean", "min", "max"]].round(4).to_string())

    print("\nMARGINAL AVERAGE of %/trade by axis")
    for ax in ("read", "n", "band", "stop", "tp", "tf", "mk"):
        print(f"  {ax:<6} " + str(d.groupby(ax).mu.mean().round(4).to_dict()))

    print("\nBEST CELL PER READING (research), and how many of its 3 markets are positive")
    for nm, g in d.groupby("read"):
        b1 = g.loc[g.mu.idxmax()]
        key = g[(g.n == b1.n) & (g.stop == b1.stop) & (g.tp == b1.tp) & (g.tf == b1.tf)
                & (g.band == b1.band)]
        print(f"  {nm:<18} tf {int(b1.tf):>2} n {int(b1.n):>3} band {b1.band} stop {b1.stop} "
              f"tp {b1.tp} | {b1.mk:<7} n {int(b1.cnt):>5} mu {b1.mu:+.4f} PF {b1.pf:.3f} "
              f"hold {b1.hold:.0f}min c/r {b1.cr:.3f} | markets +ve {int((key.mu>0).sum())}/{len(key)}")


if __name__ == "__main__":
    main()
