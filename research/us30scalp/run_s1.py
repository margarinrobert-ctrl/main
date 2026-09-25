"""S1 -- the arithmetic gate, before any rule.

Order is deliberate. (1) what the round turn costs as a fraction of the stop, and the break-even
win rate each geometry implies; (2) what the POPULATION delivers at that geometry, which is the
ceiling any trigger is climbing toward; (3) GROSS against NET, because a filter moves net toward
gross and can never pass it; (4) the hours inside the window; (5) the window and the flatten
separated, which `STUDY_V61_SESSION` showed are different questions with different answers.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 220)

GEOS = [(0.5, 0.5), (0.75, 0.75), (1.0, 1.0), (1.0, 2.0), (1.5, 1.5), (1.5, 3.0),
        (2.0, 2.0), (2.5, 2.5), (3.0, 3.0)]


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    win = S.window(f)
    print(f"US30L {len(f):,} bars   window 07:00-11:00 = {win.sum():,} bars "
          f"({100*win.mean():.1f}%)   sessions {f.index[win].normalize().nunique():,}")

    # ---- 1. the arithmetic ------------------------------------------------------------------
    print("\n=== 1. what the geometry costs, in the window, on the research block ===")
    m = bl["A_research"] & win
    atr = np.nanmedian(f["atr"].to_numpy()[m])
    px = np.nanmedian(f["close"].to_numpy()[m])
    print(f"median ATR(14) in-window {atr:.2f} pts on a {px:,.0f} index; round turn "
          f"{S.COST:.2f} pts = {100*S.COST/px:.4f}% of price")
    rows = []
    for st, tg in GEOS:
        rows.append(dict(stop=f"{st}N", target=f"{tg}N", risk_pts=st * atr,
                         cost_over_risk=S.COST / (st * atr),
                         breakeven=S.breakeven(st, tg, S.COST, atr),
                         driftless=st / (st + tg)))
    A = pd.DataFrame(rows)
    A["cost_costs_pts"] = A["breakeven"] - A["driftless"]
    print(A.round(4).to_string(index=False))

    # ---- 2. what the population delivers ----------------------------------------------------
    print("\n=== 2. the POPULATION at each geometry -- every bar in the window, no rule ===")
    print("    (this is the ceiling; a trigger has to beat it, a filter cannot pass gross)")
    sig, side = S.everybar(f, side=1)
    rows = []
    for st, tg in GEOS:
        for sd, nm in ((1, "long"), (-1, "short")):
            s2, d2 = S.everybar(f, side=sd)
            for blk, bm in bl.items():
                keep = np.isin(s2, np.flatnonzero(bm))
                t = S.walk(f, s2[keep], d2[keep], stop_a=st, tgt_a=tg, cost=S.COST)
                tg0 = S.walk(f, s2[keep], d2[keep], stop_a=st, tgt_a=tg, cost=0.0)
                if not len(t):
                    continue
                r = S.summ(t, f"{st}N/{tg}N {nm}")
                r["block"] = blk
                r["gross_pts"] = float(tg0["pts"].mean())
                r["gross_pf"] = S.pf(tg0["pts"].to_numpy())
                r["be"] = S.breakeven(st, tg, S.COST, atr)
                rows.append(r)
    P = pd.DataFrame(rows)
    for blk in bl:
        sub = P[P.block == blk]
        print(f"\n-- {blk} --")
        print(sub[["rule", "n", "pts", "gross_pts", "pf", "gross_pf", "win", "res_win", "be",
                   "amb", "med_min", "flat_sh"]].round(4).to_string(index=False))

    # ---- 3. hour by hour --------------------------------------------------------------------
    print("\n=== 3. the hours inside 07:00-11:00, population long, 1.5N/1.5N ===")
    slots = [(420, 480, "07:00-08:00"), (480, 540, "08:00-09:00"), (540, 570, "09:00-09:30"),
             (570, 600, "09:30-10:00"), (600, 660, "10:00-11:00"), (420, 660, "ALL 07-11")]
    rows = []
    for m0, m1, nm in slots:
        s2, d2 = S.everybar(f, side=1)
        for blk, bm in bl.items():
            keep = np.isin(s2, np.flatnonzero(bm))
            t = S.walk(f, s2[keep], d2[keep], stop_a=1.5, tgt_a=1.5, m0=m0, m1=m1, cost=S.COST)
            t0 = S.walk(f, s2[keep], d2[keep], stop_a=1.5, tgt_a=1.5, m0=m0, m1=m1, cost=0.0)
            if not len(t):
                continue
            rows.append(dict(slot=nm, block=blk, n=len(t), pts=t["pts"].mean(),
                             gross=t0["pts"].mean(), pf=S.pf(t["pts"].to_numpy()),
                             win=float((t["pts"] > 0).mean())))
    H = pd.DataFrame(rows)
    print(H.round(4).pivot(index="slot", columns="block",
                           values=["n", "pts", "gross", "pf"]).round(3).to_string())

    # ---- 4. the window and the flatten, separated -------------------------------------------
    print("\n=== 4. window and flatten are different questions (Donchian 20 long, 1.5N/1.5N) ===")
    s2, d2 = S.donchian(f, 20, 1)
    rows = []
    for nm, m0, m1, fl in (("all hours, no flatten", -1, -1, 0),
                           ("07-11 window, no flatten", S.W0, S.W1, 0),
                           ("07-11 window + flat 11:00", S.W0, S.W1, S.FLAT),
                           ("all hours + flat 11:00", -1, -1, S.FLAT)):
        for blk, bm in bl.items():
            keep = np.isin(s2, np.flatnonzero(bm))
            t = S.walk(f, s2[keep], d2[keep], stop_a=1.5, tgt_a=1.5, hold=0 if fl else 16,
                       m0=m0, m1=m1, flat=fl, cost=S.COST)
            if not len(t):
                continue
            r = S.summ(t, nm); r["block"] = blk
            rows.append(r)
    W = pd.DataFrame(rows)
    print(W[["rule", "block", "n", "pts", "pct", "pf", "win", "med_min",
             "stop_sh", "tgt_sh", "flat_sh"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
