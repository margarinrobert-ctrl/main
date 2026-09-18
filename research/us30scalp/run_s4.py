"""S4 -- the user's actual definition: 20 to 150 POINTS, up to 4 hours, entries 07:00-11:00.

S1-S3 tested ATR-multiple barriers and called the wide end "not a scalp". That was my framing, not
the user's: on US30's 31.17-point in-window ATR, **20 points is 0.64N and 150 points is 4.81N**, and
four hours is exactly the 16-bar cap. So the whole of §4's marginal consensus already sits INSIDE
this definition and the space below is the one that should have been swept first.

TWO PARAMETERISATIONS, BOTH RUN, because `STUDY_DL50` found they disagree about whether a US30
result in this very window decays at all: a fixed 50-point stop is 4.23 ATR in 2016 and 1.10 ATR in
2025, so a points grid quietly changes geometry across the sample while an ATR grid does not.

The hold cap BINDS here rather than a session flatten -- "up to 4 hours" is a cap, not a bell -- so
entries are 07:00-11:00 and a trade may run past 11:00 to its cap.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 240)
PTS = (20, 30, 40, 50, 75, 100, 150)
TGT_PTS = (20, 30, 40, 50, 75, 100, 150, 0)      # 0 = no target
HOLDS = (4, 8, 16)                                # 1h, 2h, 4h


def grid(f, mask, trig, use_pts=1, stops=PTS, tgts=TGT_PTS):
    s2, d2 = trig(f)
    keep = np.isin(s2, np.flatnonzero(mask))
    s2, d2 = s2[keep], d2[keep]
    out = []
    for st in stops:
        for tg in tgts:
            for hd in HOLDS:
                t = S.walk(f, s2, d2, stop_a=st, tgt_a=tg if tg > 0 else 1e9, hold=hd,
                           flat=0, use_pts=use_pts)
                if len(t) < 40:
                    continue
                out.append(dict(stop=st, target=tg, hold_h=hd * 0.25, n=len(t),
                                pts=t["pts"].mean(), pct=t["pct"].mean(),
                                pf=S.pf(t["pts"].to_numpy()),
                                win=float((t["pts"] > 0).mean()),
                                med_min=float(t["mins"].median()),
                                amb=float(t["amb"].mean()),
                                cap_sh=float((t.why == 2).mean())))
    return pd.DataFrame(out)


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res = bl["A_research"]
    win = S.window(f)
    atr = np.nanmedian(f["atr"].to_numpy()[res & win])

    # ---- 1. the range, in both units --------------------------------------------------------
    print(f"=== 1. 20-150 points on a {atr:.2f}-point in-window ATR, and what each costs ===")
    rows = []
    for st in PTS:
        rows.append(dict(stop_pts=st, in_ATR=st / atr, cost_over_risk=S.COST / st,
                         be_1to1=(st + S.COST) / (2 * st),
                         be_1to2=(st + S.COST) / (3 * st),
                         be_1to3=(st + S.COST) / (4 * st)))
    print(pd.DataFrame(rows).round(4).to_string(index=False))
    print("\n(the ATR column drifts across the sample: STUDY_DL50 measured a fixed 50-pt stop at\n"
          " 4.23 ATR in 2016 and 1.10 ATR in 2025, so a points grid is not one geometry)")

    # ---- 2. the population over the user's space --------------------------------------------
    print("\n=== 2. the POPULATION over that space (every in-window bar, long, research) ===")
    P = grid(f, res, lambda g: S.everybar(g, 1))
    print(f"{len(P)} cells   profitable {100*(P.pts > 0).mean():.1f}%   best PF {P.pf.max():.3f}")
    for ax in ("stop", "target", "hold_h"):
        print(f"\n-- population marginal, {ax} --")
        print(P.groupby(ax).agg(cells=("pts", "size"), pts=("pts", "mean"),
                                pf=("pf", "mean"), n=("n", "mean")).round(4).to_string())

    # ---- 3. the same space with a trigger ---------------------------------------------------
    print("\n=== 3. Donchian 20 long over the same space, RESEARCH ONLY, marginal averages ===")
    G = grid(f, res, S.TRIGGERS["donch20 long"])
    print(f"{len(G)} cells   profitable {100*(G.pts > 0).mean():.1f}%   best PF {G.pf.max():.3f}   "
          f"median PF {G.pf.median():.3f}")
    for ax in ("stop", "target", "hold_h"):
        print(f"\n-- {ax} --")
        print(G.groupby(ax).agg(cells=("pts", "size"), pts=("pts", "mean"), pf=("pf", "mean"),
                                n=("n", "mean"), med_min=("med_min", "mean")).round(4).to_string())
    print("\ntop 12 by profit factor:")
    print(G.sort_values("pf", ascending=False).head(12).round(4).to_string(index=False))

    # ---- 4. points against ATR, matched at the median ---------------------------------------
    print("\n=== 4. POINTS vs ATR parameterisation, matched at the median in-window ATR ===")
    A = grid(f, res, S.TRIGGERS["donch20 long"], use_pts=0,
             stops=tuple(round(p / atr, 3) for p in PTS),
             tgts=tuple(round(p / atr, 3) if p else 0 for p in TGT_PTS))
    print(f"points grid: profitable {100*(G.pts>0).mean():.1f}%  mean PF {G.pf.mean():.4f}  "
          f"best {G.pf.max():.3f}")
    print(f"ATR grid   : profitable {100*(A.pts>0).mean():.1f}%  mean PF {A.pf.mean():.4f}  "
          f"best {A.pf.max():.3f}")
    for ax in ("stop", "target"):
        a = A.groupby(ax).pts.mean()
        g = G.groupby(ax).pts.mean()
        print(f"\n-- {ax}: points marginal vs the SAME distance in ATR --")
        print(pd.DataFrame({"points_grid": g.to_numpy(), "atr_grid": a.to_numpy()},
                           index=[f"{p} pts / {p/atr:.2f}N" for p in
                                  (PTS if ax == 'stop' else TGT_PTS)]).round(4).to_string())


if __name__ == "__main__":
    main()
