"""S3 -- if the scalp geometry is what loses, what does this window support?

S1/S2 settled the negative half: the in-window population is short of its own break-even at every
geometry, no declared trigger beats a matched random entry (0 of 21), and at scalp barriers the
intrabar convention is worth more than any edge on offer. So the constructive question is what
geometry -- if any -- the 07:00-11:00 window DOES support, read by marginal average and not by a
top row, with `no target` included because it has won 24 times on this branch.

Then one read of the survivor on the holdout AND on US30_ISO's post-2025-07 span, a DIFFERENT
PROVIDER no search here has touched.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 220)
STOPS = (1.0, 1.5, 2.0, 2.5, 3.0)
TGTS = (1.0, 1.5, 2.0, 3.0, 0.0)        # 0.0 = NO TARGET
HOLDS = (4, 8, 16, 0)                    # bars; 0 = none (flatten or barrier only)
FLATS = (S.FLAT, 0)


def cells(f, mask, trig, m0=S.W0, m1=S.W1):
    s2, d2 = trig(f)
    keep = np.isin(s2, np.flatnonzero(mask))
    s2, d2 = s2[keep], d2[keep]
    out = []
    for st in STOPS:
        for tg in TGTS:
            for hd in HOLDS:
                for fl in FLATS:
                    if hd == 0 and fl == 0:
                        continue           # nothing would ever close a no-target trade
                    t = S.walk(f, s2, d2, stop_a=st, tgt_a=tg if tg > 0 else 999.0,
                               hold=hd, m0=m0, m1=m1, flat=fl)
                    if len(t) < 40:
                        continue
                    out.append(dict(stop=st, target=tg, hold=hd, flat=int(fl > 0), n=len(t),
                                    pts=t["pts"].mean(), pct=t["pct"].mean(),
                                    pf=S.pf(t["pts"].to_numpy()),
                                    win=float((t["pts"] > 0).mean()),
                                    med_min=float(t["mins"].median()),
                                    amb=float(t["amb"].mean())))
    return pd.DataFrame(out)


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res, hold_ = bl["A_research"], bl["B_holdout"]

    print("=== 1. geometry sweep on the window, Donchian 20 long, RESEARCH ONLY ===")
    G = cells(f, res, S.TRIGGERS["donch20 long"])
    print(f"{len(G)} scorable cells   profitable {100*(G.pts > 0).mean():.1f}%   "
          f"best PF {G.pf.max():.3f}   median PF {G.pf.median():.3f}")
    print("\nMARGINAL AVERAGE per axis (never the top row):")
    for ax in ("stop", "target", "hold", "flat"):
        mg = G.groupby(ax).agg(cells=("pts", "size"), pts=("pts", "mean"), pf=("pf", "mean"),
                               n=("n", "mean")).round(4)
        print(f"\n-- {ax} --"); print(mg.to_string())

    print("\ntop 10 by profit factor:")
    print(G.sort_values("pf", ascending=False).head(10).round(4).to_string(index=False))

    # ---- 2. the marginal consensus, read once ------------------------------------------------
    best_stop = G.groupby("stop").pts.mean().idxmax()
    best_tgt = G.groupby("target").pts.mean().idxmax()
    best_hold = G.groupby("hold").pts.mean().idxmax()
    best_flat = G.groupby("flat").pts.mean().idxmax()
    print(f"\n=== 2. MARGINAL CONSENSUS: stop {best_stop}N, target "
          f"{'none' if best_tgt == 0 else str(best_tgt)+'N'}, hold {best_hold}, "
          f"flatten {'on' if best_flat else 'off'} ===")
    kw = dict(stop_a=best_stop, tgt_a=best_tgt if best_tgt > 0 else 999.0,
              hold=int(best_hold), flat=S.FLAT if best_flat else 0)

    rows = []
    for feed, name in ((f, "US30L"), (S.load("US30I"), "US30I")):
        blk = S.blocks(feed, name)
        for bn, bm in blk.items():
            s2, d2 = S.TRIGGERS["donch20 long"](feed)
            keep = np.isin(s2, np.flatnonzero(bm))
            t = S.walk(feed, s2[keep], d2[keep], **kw)
            if len(t) < 20:
                continue
            elig = S.window(feed) & bm
            ctl = S.control(feed, len(t), t["side"].to_numpy(), elig, n_draw=400, seed=11, **kw)
            base = S.walk(feed, *S.everybar(feed, 1), **kw)
            base = base[np.isin(base.e_bar - 1, np.flatnonzero(bm))]
            rows.append(dict(feed=name, block=bn, n=len(t), pts=t["pts"].mean(),
                             pct=t["pct"].mean(), pf=S.pf(t["pts"].to_numpy()),
                             win=float((t["pts"] > 0).mean()), med_min=t["mins"].median(),
                             ctl=float(np.median(ctl)) if ctl is not None else np.nan,
                             p=float(np.mean(ctl >= t["pts"].mean())) if ctl is not None else np.nan,
                             alwaysin=float(base["pts"].mean()) if len(base) else np.nan))
    R = pd.DataFrame(rows)
    print(R.round(4).to_string(index=False))

    # ---- 3. what cost would it take? ---------------------------------------------------------
    print("\n=== 3. the cost the consensus cell would need to break even ===")
    s2, d2 = S.TRIGGERS["donch20 long"](f)
    keep = np.isin(s2, np.flatnonzero(res))
    for mult in (0.0, 0.25, 0.5, 1.0, 2.0):
        t = S.walk(f, s2[keep], d2[keep], cost=S.COST * mult, **kw)
        print(f"  cost x{mult:<4}  ({S.COST*mult:5.2f} pts)  {t['pts'].mean():+8.4f} pts   "
              f"PF {S.pf(t['pts'].to_numpy()):.4f}")


if __name__ == "__main__":
    main()
