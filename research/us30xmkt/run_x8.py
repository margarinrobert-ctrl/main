"""x8 -- a THIRD frozen condition, declared by the rate workstream and read once here.

PROVENANCE, STATED SO IT CANNOT BE MISREAD. H1 and H2 were declared in `run_x3.py` before any of
these markets was read, and section 1 of the study reports them EXACTLY as declared whatever this
file finds. This third condition arrived AFTER that read, from `research/us30rate/` (sections 14-15
of `STUDY_US30_SCALP_0711`), which varied the entry channel on US30 and found:

  * `+adx<=20` beats its own same-selectivity null in 15 of 18 channel x block cells but only 3 of
    6 on the RESERVED forward feed (median p 0.617 there) -- and the 12/12 record the base-rates
    workstream reported was measured at CHANNEL 20 ONLY.
  * `+ema align` is 18 of 18 including 6/6 on the forward feed.
  * The EMA stack is ONE INEQUALITY: `ema34>ema89` alone is 3/3 blocks with the table's best p
    (0.030), while `ema13>ema34` alone is 9/18 cells at median p 0.575 and mean PF exactly 1.000.
    Head to head the slow half beats the full alignment in only 6 of 18 cells -- dropping the
    13-EMA is FREE, not better.

So the third condition is `ema34>ema89`, carried because it is the SIMPLEST form of the one
component that travelled and because it is far milder (it keeps ~2/3 of signals against the ADX
ceiling's ~1/4), which is what decides whether anything is readable on a market with few trades.
`ema13>ema34` alone is run beside it as the falsifier -- if the slow half is the whole condition,
the fast half must be worth nothing.

All of that evidence is US30. These four markets chose none of it, so this is still a genuine
out-of-sample read; it is simply a WEAKER pre-declaration than H1 and H2, and it is labelled that
way in the study. Same frozen geometry, same walker, same nulls. 28 further declared cells.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xm_core as X  # noqa: E402

pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 60)

print("=" * 100)
print("x8  THE THIRD FROZEN CONDITION: ema34>ema89, with ema13>ema34 as its falsifier")
print("=" * 100)

F = X.load_all()
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}


def masks3(f):
    """The frozen masks PLUS the two halves of the alignment, split exactly as the rate
    workstream split them. Nothing else changes."""
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    M = X.build_masks(h, l, c)
    e13, e34, e89 = X.ema(c, 13), X.ema(c, 34), X.ema(c, 89)
    M["ema34>89"] = e34 > e89
    M["ema13>34"] = e13 > e34
    return M


ARMS3 = [("base", []), ("+ema align", ["ema align"]),
         ("+ema34>89", ["ema34>89"]), ("+ema13>34", ["ema13>34"]),
         ("+adx<=20", ["adx<=20"])]

rows = []
for m in X.MARKETS:
    f = F[m]
    M = masks3(f)
    for b, ix in BL[m].items():
        elig = X.eligible(f, ix)
        for param in ("atr", "pts"):
            for arm, conds in ARMS3:
                t = X.trades(f, m, conds, param=param, bm=ix, M=M)
                s = X.summarise(t, f"{m}|{b}|{param}|{arm}")
                s.update(market=m, block=b, param=param, arm=arm)
                sg, _ = X.signals(f, conds, bm=ix, M=M)
                mod = f["mod"].to_numpy()[sg]
                sg = sg[(mod >= X.W0) & (mod < X.W1)]
                sb, _ = X.signals(f, [], bm=ix, M=M)
                modb = f["mod"].to_numpy()[sb]
                sb = sb[(modb >= X.W0) & (modb < X.W1)]
                s["kept"] = len(sg) / max(len(sb), 1)
                if len(t) >= 10:
                    ctl = X.control(f, m, len(t), elig, param=param, n_draw=400, seed=17)
                    if ctl is not None and len(ctl) > 20:
                        s["ctl_med"] = float(np.median(ctl[:, 0]))
                        s["ctl_p"] = float((ctl[:, 0] >= s["mean"]).mean())
                    s["boot_p"] = X.boot_days(t, "atr_u", n=1500, seed=23)["p"]
                rows.append(s)
        print(f"    {m:6s} {b:12s} done")

R = pd.DataFrame(rows)
cols = ["market", "block", "param", "arm", "n", "kept", "mean", "t", "mde80", "pf", "win",
        "pts", "ctl_med", "ctl_p", "boot_p"]
for p in ("atr", "pts"):
    print(f"\n=== {p.upper()} parameterisation, ATR units per trade ===")
    print(R[R.param == p][cols].round(4).to_string(index=False))

print("\n--- the head-to-head, ATR units, on the four markets that chose nothing -----------")
RN = R[R.market.isin(X.NEW_MARKETS)]
piv = RN.pivot_table(index=["market", "block", "param"], columns="arm", values="mean")
for a in ("+ema align", "+ema34>89", "+ema13>34", "+adx<=20"):
    piv[f"d {a}"] = piv[a] - piv["base"]
print(piv.round(4).to_string())

print("\n--- counts against base, and against the full alignment ----------------------------")
out = []
for a in ("+ema align", "+ema34>89", "+ema13>34", "+adx<=20"):
    out.append(dict(arm=a, cells=len(piv),
                    beats_base=int((piv[a] > piv["base"]).sum()),
                    positive=int((piv[a] > 0).sum()),
                    beats_full_align=int((piv[a] > piv["+ema align"]).sum()),
                    mean_edge=float((piv[a] - piv["base"]).mean())))
print(pd.DataFrame(out).round(4).to_string(index=False))

print("\n    US30 reference (spent blocks, printed for comparison only):")
piv30 = R[R.market.isin(["US30"])].pivot_table(index=["block", "param"], columns="arm",
                                               values="mean")
print(piv30.round(4).to_string())

C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
R.to_csv(f"{C}/x8_third.csv", index=False)
print(f"\n    wrote {C}/x8_third.csv")
