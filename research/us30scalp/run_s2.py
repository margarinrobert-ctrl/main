"""S2 -- the tie-break bracket, then every declared trigger against the population it sits in.

S1 established that the in-window POPULATION is short of its own break-even at every geometry and
that gross profit factor approaches 1.0 from BELOW as the barriers widen. Two things follow.

(1) At scalp geometry 14.0% of trades touch both barriers inside one 15-minute bar, so the
    convention decides them. `STUDY_VOLBO_BREAKOUT` found that convention worth twice an entire
    edge and settled it on finer data -- which is unavailable here -- so the honest move is to
    report the BRACKET: stop-first and target-first are the two ends, and if the verdict differs
    between them the truth is not knowable at this resolution.

(2) Gross is the ceiling, so a trigger has to beat the population rather than a filter improving
    it. Seven declared triggers x three MEASURABLE geometries, research block only, each against
    a matched random entry drawn from the same eligible in-window bars.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 220)
GEOS = [(1.0, 1.0), (1.5, 1.5), (2.0, 2.0)]
SCALP = [(0.5, 0.5), (0.75, 0.75), (1.0, 1.0)]


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    win = S.window(f)
    res = bl["A_research"]

    # ---- 1. the tie-break bracket -----------------------------------------------------------
    print("=== 1. the intrabar convention BRACKETS the scalp verdict (population, research) ===")
    rows = []
    for st, tg in SCALP + GEOS:
        s2, d2 = S.everybar(f, 1)
        keep = np.isin(s2, np.flatnonzero(res))
        a = S.walk(f, s2[keep], d2[keep], stop_a=st, tgt_a=tg, tie=0)
        b = S.walk(f, s2[keep], d2[keep], stop_a=st, tgt_a=tg, tie=1)
        rows.append(dict(geo=f"{st}N/{tg}N", n=len(a), amb=float(a["amb"].mean()),
                         stop_first_pts=a["pts"].mean(), target_first_pts=b["pts"].mean(),
                         stop_first_pf=S.pf(a["pts"].to_numpy()),
                         target_first_pf=S.pf(b["pts"].to_numpy()),
                         spread_pts=b["pts"].mean() - a["pts"].mean()))
    B = pd.DataFrame(rows)
    print(B.round(4).to_string(index=False))
    print("\nthe spread is what the CONVENTION is worth; compare it to the edge being claimed.")

    # ---- 2. every declared trigger against a matched random entry ---------------------------
    print("\n=== 2. seven declared triggers x three geometries, RESEARCH ONLY, vs a matched "
          "random entry drawn from the same eligible in-window bars (400 draws) ===")
    elig = win & res
    rows = []
    for nm, fn in S.TRIGGERS.items():
        s2, d2 = fn(f)
        keep = np.isin(s2, np.flatnonzero(res))
        s2, d2 = s2[keep], d2[keep]
        for st, tg in GEOS:
            t = S.walk(f, s2, d2, stop_a=st, tgt_a=tg)
            if len(t) < 40:
                continue
            ctl = S.control(f, len(t), t["side"].to_numpy(), elig, n_draw=400, seed=7,
                            stop_a=st, tgt_a=tg)
            p = float(np.mean(ctl >= t["pts"].mean())) if ctl is not None and len(ctl) else np.nan
            rows.append(dict(trigger=nm, geo=f"{st}N/{tg}N", n=len(t),
                             pts=t["pts"].mean(), pf=S.pf(t["pts"].to_numpy()),
                             win=float((t["pts"] > 0).mean()),
                             ctl_pts=float(np.median(ctl)) if ctl is not None else np.nan,
                             excess=t["pts"].mean() - (float(np.median(ctl)) if ctl is not None else np.nan),
                             p=p))
    T = pd.DataFrame(rows).sort_values("p")
    print(T.round(4).to_string(index=False))
    k = int((T["p"] <= 0.05).sum())
    print(f"\ncells clearing p<=0.05: {k} of {len(T)}   expected by chance {0.05*len(T):.1f}")

    # ---- 3. and does anything beat ALWAYS-IN in the same window? ----------------------------
    print("\n=== 3. the same triggers against ALWAYS-IN long in the window (the drift baseline) ===")
    for st, tg in GEOS:
        s2, d2 = S.everybar(f, 1)
        keep = np.isin(s2, np.flatnonzero(res))
        base = S.walk(f, s2[keep], d2[keep], stop_a=st, tgt_a=tg)
        print(f"  {st}N/{tg}N  always-in long: n={len(base):5d}  {base['pts'].mean():+.4f} pts  "
              f"PF {S.pf(base['pts'].to_numpy()):.4f}")


if __name__ == "__main__":
    main()
