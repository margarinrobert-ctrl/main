"""x6 -- why the same arm reads differently in points and in ATR units, on US30 itself.

x3 turned up something the section-12 tables could not show, because they were scored in POINTS:
under the MATCHED geometry `+adx<=20` earns MORE POINTS than the base on US30 and FEWER ATR UNITS.
That is the shape of an R-DENOMINATOR effect -- `STUDY_SWEEP_110K` found 94% of a breakout's
apparent contribution was the denominator, and `STUDY_V63` found the stop axis gives three
different answers in three units. This measures it directly rather than asserting it: the ATR at
the signal bar, per arm, per market.

If `adx<=20` selects HIGHER-ATR bars then a fixed 50-point stop is a TIGHTER stop in ATR terms on
those bars, the trade risks less and its point result is not comparable to the base's; and under
the matched ATR geometry it risks MORE points per trade, so it makes more points for the same
risk-adjusted return. Either way the points column is measuring bar volatility, not the filter.
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
print("x6  THE UNIT DECOMPOSITION -- does the ADX ceiling select bars with a different ATR?")
print("=" * 100)

F = X.load_all()
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}
MASK = {m: X.build_masks(F[m]["high"].to_numpy(), F[m]["low"].to_numpy(),
                         F[m]["close"].to_numpy()) for m in X.MARKETS}

rows = []
for m in X.MARKETS:
    f = F[m]
    at = f["atr"].to_numpy()
    for b, ix in BL[m].items():
        base_atr = None
        for arm, conds in X.ARMS:
            s, _ = X.signals(f, conds, bm=ix, M=MASK[m])
            mod = f["mod"].to_numpy()[s]
            s = s[(mod >= X.W0) & (mod < X.W1)]
            if len(s) < 20:
                continue
            a = float(np.median(at[s]))
            if arm == "base":
                base_atr = a
            t_atr = X.trades(f, m, conds, param="atr", bm=ix, M=MASK[m])
            t_pts = X.trades(f, m, conds, param="pts", bm=ix, M=MASK[m])
            rows.append(dict(
                market=m, block=b, arm=arm, n_sig=len(s), med_atr_sig=a,
                atr_vs_base=a / base_atr if base_atr else np.nan,
                med_risk_ATRparam=float(t_atr["risk"].median()) if len(t_atr) else np.nan,
                pts_ATRparam=float(t_atr["pts"].mean()) if len(t_atr) else np.nan,
                atru_ATRparam=float(t_atr["atr_u"].mean()) if len(t_atr) else np.nan,
                pts_PTSparam=float(t_pts["pts"].mean()) if len(t_pts) else np.nan,
                atru_PTSparam=float(t_pts["atr_u"].mean()) if len(t_pts) else np.nan))
D = pd.DataFrame(rows)
print("\n--- 1. median ATR at the signal bar, per arm, relative to the base arm ------------")
print(D[["market", "block", "arm", "n_sig", "med_atr_sig", "atr_vs_base",
         "med_risk_ATRparam"]].round(4).to_string(index=False))

print("\n--- 2. the same arm in two units under BOTH parameterisations ----------------------")
print(D[["market", "block", "arm", "pts_ATRparam", "atru_ATRparam",
         "pts_PTSparam", "atru_PTSparam"]].round(4).to_string(index=False))

print("\n--- 3. the ADX arm's ATR selection, summarised -------------------------------------")
piv = D[D.arm.isin(["base", "+adx<=20", "+ema align", "conventional"])].pivot_table(
    index=["market", "block"], columns="arm", values="med_atr_sig")
piv["adx/base"] = piv["+adx<=20"] / piv["base"]
piv["conv/base"] = piv["conventional"] / piv["base"]
print(piv.round(4).to_string())
print(f"\n    mean ATR ratio, adx<=20 vs base, over 9 market-blocks: "
      f"{piv['adx/base'].mean():.4f}   (>1 means it selects MORE volatile bars)")
print(f"    mean ATR ratio, conventional vs base:                   "
      f"{piv['conv/base'].mean():.4f}")

print("\n--- 4. the sign disagreement between units, counted --------------------------------")
b = D[D.arm == "base"].set_index(["market", "block"])
cnt = []
for arm in ("+adx<=20", "+ema align", "+both", "conventional"):
    a = D[D.arm == arm].set_index(["market", "block"])
    j = a.join(b, rsuffix="_b").dropna(subset=["pts_ATRparam", "pts_ATRparam_b"])
    cnt.append(dict(arm=arm, cells=len(j),
                    beats_base_PTS_unit=int((j.pts_ATRparam > j.pts_ATRparam_b).sum()),
                    beats_base_ATR_unit=int((j.atru_ATRparam > j.atru_ATRparam_b).sum()),
                    units_disagree=int(((j.pts_ATRparam > j.pts_ATRparam_b) !=
                                        (j.atru_ATRparam > j.atru_ATRparam_b)).sum())))
print(pd.DataFrame(cnt).to_string(index=False))
print("\n    `units_disagree` counts cells where the POINTS column and the ATR-UNIT column")
print("    disagree about whether the arm beat its base -- on the SAME trades, same geometry.")

C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
D.to_csv(f"{C}/x6_units.csv", index=False)
print(f"\n    wrote {C}/x6_units.csv")
