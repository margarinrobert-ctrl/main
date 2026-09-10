"""S5 -- the control, and one read, inside the user's own definition.

S4 changed the picture. Over 20-150 points and up to four hours the Donchian 20 long has **45.2%
of 168 cells profitable against the population's 2.4%**, and beats the population's marginal by
+2.7 to +3.7 points at every setting. That is the first separation anywhere in this study -- but
"beats every bar in the window" is not the null, because a trigger that fires 1,200 times against
a population of 5,400 is also trading less. The null is a matched random entry: same count, same
side, same eligible in-window bars, sorted.

Declared finalists are taken from the MARGINAL AVERAGE per axis, never the top row, plus the two
corners the marginals point at. Research only; survivors read ONCE on the holdout and on
US30_ISO's post-2025-07 span, a different provider.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 240)

# declared from S4's marginals: stop wide, target none-or-wide, cap 4h
FINALS = [
    ("marginal consensus", dict(stop_a=150, tgt_a=1e9, hold=16)),
    ("wide stop, 150 target", dict(stop_a=150, tgt_a=150, hold=16)),
    ("100 stop, no target", dict(stop_a=100, tgt_a=1e9, hold=16)),
    ("100 stop, 100 target", dict(stop_a=100, tgt_a=100, hold=16)),
    ("75 stop, no target", dict(stop_a=75, tgt_a=1e9, hold=16)),
    ("50 stop, 150 target", dict(stop_a=50, tgt_a=150, hold=16)),
    ("30 stop, 150 target", dict(stop_a=30, tgt_a=150, hold=16)),
    ("50 stop, 100 target", dict(stop_a=50, tgt_a=100, hold=16)),
]
KW = dict(flat=0, use_pts=1)


def run(f, mask, trig, kw):
    s2, d2 = trig(f)
    keep = np.isin(s2, np.flatnonzero(mask))
    return S.walk(f, s2[keep], d2[keep], **kw, **KW)


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res, hol = bl["A_research"], bl["B_holdout"]
    win = S.window(f)

    # ---- 1. every trigger at the consensus geometry ------------------------------------------
    print("=== 1. all seven declared triggers at the marginal consensus "
          "(150-pt stop, no target, 4h cap), RESEARCH, vs a matched random entry ===")
    kw = FINALS[0][1]
    rows = []
    for nm, fn in S.TRIGGERS.items():
        t = run(f, res, fn, kw)
        if len(t) < 40:
            continue
        ctl = S.control(f, len(t), t["side"].to_numpy(), win & res, n_draw=400, seed=3,
                        **kw, **KW)
        rows.append(dict(trigger=nm, n=len(t), pts=t["pts"].mean(), pct=t["pct"].mean(),
                         pf=S.pf(t["pts"].to_numpy()), win=float((t["pts"] > 0).mean()),
                         med_min=t["mins"].median(),
                         ctl=float(np.median(ctl)), excess=t["pts"].mean() - float(np.median(ctl)),
                         p=float(np.mean(ctl >= t["pts"].mean()))))
    T = pd.DataFrame(rows).sort_values("p")
    print(T.round(4).to_string(index=False))
    print(f"\nclearing p<=0.05: {int((T.p <= 0.05).sum())} of {len(T)}   "
          f"expected {0.05*len(T):.1f}")

    # ---- 2. the eight declared geometries, best trigger, with the control --------------------
    best_trig = T.iloc[0]["trigger"]
    print(f"\n=== 2. eight declared geometries on `{best_trig}`, RESEARCH, vs the same control ===")
    rows = []
    for nm, kw2 in FINALS:
        t = run(f, res, S.TRIGGERS[best_trig], kw2)
        if len(t) < 40:
            continue
        ctl = S.control(f, len(t), t["side"].to_numpy(), win & res, n_draw=400, seed=5,
                        **kw2, **KW)
        rows.append(dict(geo=nm, n=len(t), pts=t["pts"].mean(), pct=t["pct"].mean(),
                         pf=S.pf(t["pts"].to_numpy()), win=float((t["pts"] > 0).mean()),
                         med_min=t["mins"].median(), cap_sh=float((t.why == 2).mean()),
                         ctl=float(np.median(ctl)), excess=t["pts"].mean() - float(np.median(ctl)),
                         p=float(np.mean(ctl >= t["pts"].mean()))))
    G = pd.DataFrame(rows).sort_values("p")
    print(G.round(4).to_string(index=False))
    print(f"\nclearing p<=0.05: {int((G.p <= 0.05).sum())} of {len(G)}   "
          f"expected {0.05*len(G):.1f}")

    # ---- 3. ONE READ -------------------------------------------------------------------------
    print("\n=== 3. ONE READ of the two best-shaped cells: holdout, and US30_ISO forward ===")
    picks = [(G.iloc[0]["geo"], dict(FINALS)[G.iloc[0]["geo"]])]
    if G.iloc[0]["geo"] != "marginal consensus":
        picks.append(("marginal consensus", FINALS[0][1]))
    rows = []
    for pname, kw2 in picks:
        for feed, fname in ((f, "US30L"), (S.load("US30I"), "US30I")):
            blk = S.blocks(feed, fname)
            for bn, bm in blk.items():
                t = run(feed, bm, S.TRIGGERS[best_trig], kw2)
                if len(t) < 20:
                    continue
                ctl = S.control(feed, len(t), t["side"].to_numpy(), S.window(feed) & bm,
                                n_draw=400, seed=9, **kw2, **KW)
                base = run(feed, bm, lambda g: S.everybar(g, 1), kw2)
                rows.append(dict(cell=pname, feed=fname, block=bn, n=len(t),
                                 pts=t["pts"].mean(), pct=t["pct"].mean(),
                                 pf=S.pf(t["pts"].to_numpy()),
                                 win=float((t["pts"] > 0).mean()),
                                 ctl=float(np.median(ctl)),
                                 p=float(np.mean(ctl >= t["pts"].mean())),
                                 alwaysin=float(base["pts"].mean()) if len(base) else np.nan))
    R = pd.DataFrame(rows)
    print(R.round(4).to_string(index=False))

    # ---- 4. day-block bootstrap on the survivor ---------------------------------------------
    print("\n=== 4. day-block bootstrap against ZERO (the other question) ===")
    for pname, kw2 in picks:
        for bn, bm in (("A_research", res), ("B_holdout", hol)):
            t = run(f, bm, S.TRIGGERS[best_trig], kw2)
            if len(t) < 20:
                continue
            d = t.groupby(t.ts.dt.normalize())["pts"].sum().to_numpy()
            rng = np.random.default_rng(2)
            bs = np.array([rng.choice(d, len(d), replace=True).mean() for _ in range(4000)])
            print(f"  {pname:22s} {bn:11s} n={len(t):4d}  mean/day {d.mean():+7.3f}  "
                  f"P(<=0) {np.mean(bs <= 0):.3f}  CI [{np.percentile(bs,2.5):+.2f}, "
                  f"{np.percentile(bs,97.5):+.2f}]")


if __name__ == "__main__":
    main()
