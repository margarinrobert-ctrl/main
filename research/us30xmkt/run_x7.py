"""x7 -- which weighting is doing the work, on the cell section 12's headline came from.

x6 found ONE cell of nine where the points column and the ATR-unit column disagree about whether
`+adx<=20` beat its base, and it is US30's RESEARCH block -- the cell section 12's +6.260 came
from. Two readings of the same trades cannot both be the summary, so the question is which
weighting the disagreement lives in.

  mean(pts)          weights every trade by the DOLLARS it made, so a high-ATR trade counts more.
  mean(pts / ATR)    weights every trade EQUALLY at constant risk -- what one contract sized to a
                     fixed fraction of equity actually earns.
  sum(pts)/sum(ATR)  the risk-weighted aggregate: what a book that always trades ONE CONTRACT gets,
                     expressed per unit of risk. It sides with whichever trades were biggest.

`STUDY_V63` recorded that the stop axis gives three different answers in three units and the
per-trade optimum is not an optimum when the axis also moves the trade count; `STUDY_SWEEP_110K`
and `STUDY_V36` recorded R denominators collapsing. This is the same family of question asked of a
FILTER rather than of a geometry.
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
print("x7  THREE WEIGHTINGS OF THE SAME TRADES")
print("=" * 100)

F = X.load_all()
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}
MASK = {m: X.build_masks(F[m]["high"].to_numpy(), F[m]["low"].to_numpy(),
                         F[m]["close"].to_numpy()) for m in X.MARKETS}

rows = []
for m in X.MARKETS:
    for b, ix in BL[m].items():
        for param in ("pts", "atr"):
            for arm, conds in X.ARMS:
                t = X.trades(F[m], m, conds, param=param, bm=ix, M=MASK[m])
                if len(t) < 20:
                    continue
                p, a = t["pts"].to_numpy(), t["atr_sig"].to_numpy()
                rows.append(dict(market=m, block=b, param=param, arm=arm, n=len(t),
                                 mean_pts=p.mean(), mean_atru=(p / a).mean(),
                                 agg_pts_over_atr=p.sum() / a.sum(),
                                 rho_atr_pts=float(np.corrcoef(a, p)[0, 1]),
                                 med_atr=float(np.median(a))))
D = pd.DataFrame(rows)

print("\n--- US30, the cell section 12's headline came from --------------------------------")
print(D[D.market == "US30"].round(4).to_string(index=False))

print("\n--- the sign of (arm - base) in each of the three weightings, all market-blocks ----")
out = []
for (m, b, param), g in D.groupby(["market", "block", "param"]):
    base = g[g.arm == "base"].iloc[0]
    for _, r in g[g.arm != "base"].iterrows():
        out.append(dict(market=m, block=b, param=param, arm=r.arm,
                        d_pts=r.mean_pts - base.mean_pts,
                        d_atru=r.mean_atru - base.mean_atru,
                        d_agg=r.agg_pts_over_atr - base.agg_pts_over_atr))
O = pd.DataFrame(out)
O["disagree"] = (np.sign(O.d_pts) != np.sign(O.d_atru))
print(O.round(4).to_string(index=False))

print("\n--- how often the three weightings disagree, per arm -------------------------------")
S = O.groupby("arm").agg(cells=("d_pts", "size"),
                         beats_pts=("d_pts", lambda x: int((x > 0).sum())),
                         beats_atru=("d_atru", lambda x: int((x > 0).sum())),
                         beats_agg=("d_agg", lambda x: int((x > 0).sum())),
                         disagree=("disagree", "sum"))
print(S.to_string())
print(f"\n    over all {len(O)} arm x market x block x parameterisation comparisons the points and")
print(f"    ATR-unit readings disagree in {int(O.disagree.sum())} ({O.disagree.mean():.1%}).")

C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
D.to_csv(f"{C}/x7_weighting.csv", index=False)
O.to_csv(f"{C}/x7_deltas.csv", index=False)
print(f"\n    wrote {C}/x7_*.csv")
