"""x9 -- the zero-cost variant, because a negative net is not a verdict until gross is read.

CLAUDE.md's standing instruction: run the zero-cost variant before concluding there is no edge.
It matters most on gold, whose round turn is the largest fraction of its own stop here, and it is
the only way to tell a COST problem from a SIGNAL problem. Reported per market and pooled, in ATR
units, at the matched geometry -- the cost enters as a constant number of POINTS per trade, so in
ATR units it is `cost / ATR at the signal bar` and is larger exactly where the bar is calm.
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
print("x9  GROSS AGAINST NET -- is a negative cell a cost problem or a signal problem?")
print("=" * 100)

F = X.load_all()
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}
MASK = {m: X.build_masks(F[m]["high"].to_numpy(), F[m]["low"].to_numpy(),
                         F[m]["close"].to_numpy()) for m in X.MARKETS}

rows, store = [], []
for m in X.MARKETS:
    f = F[m]
    for b, ix in BL[m].items():
        for arm, conds in X.ARMS:
            t = X.trades(f, m, conds, param="atr", bm=ix, M=MASK[m])
            if len(t) < 20:
                continue
            cu = X.COST[m] / t["atr_sig"].to_numpy()      # the round turn IN ATR UNITS, per trade
            net = t["atr_u"].to_numpy()
            gross = net + cu
            rows.append(dict(market=m, block=b, arm=arm, n=len(t),
                             net=net.mean(), cost_atr=cu.mean(), gross=gross.mean(),
                             gross_pf=X.pf(gross), net_pf=X.pf(net),
                             cost_share_of_gross=(cu.mean() / gross.mean()
                                                  if gross.mean() > 0 else np.nan)))
            store.append(pd.DataFrame(dict(market=m, block=b, arm=arm, date=t["date"],
                                           net=net, gross=gross)))
D = pd.DataFrame(rows)
print("\n--- per market x block x arm, ATR units per trade ---------------------------------")
print(D.round(4).to_string(index=False))

S = pd.concat(store)
print("\n--- pooled over the four markets that chose nothing --------------------------------")
out = []
for arm, _ in X.ARMS:
    for label, sub in (("ALL 4", list(X.NEW_MARKETS)), ("DEDUP 3", ["US30I", "US100", "XAU"])):
        g = S[(S.arm == arm) & (S.market.isin(sub))]
        if len(g) < 20:
            continue
        se_n, _, _ = X.cluster_se(g.net.to_numpy(), g.date.to_numpy())
        se_g, _, _ = X.cluster_se(g.gross.to_numpy(), g.date.to_numpy())
        out.append(dict(arm=arm, set=label, n=len(g), net=g.net.mean(), gross=g.gross.mean(),
                        cost=g.gross.mean() - g.net.mean(),
                        net_mde=X.Z80 * se_n, gross_mde=X.Z80 * se_g,
                        gross_pf=X.pf(g.gross.to_numpy()), net_pf=X.pf(g.net.to_numpy())))
print(pd.DataFrame(out).round(4).to_string(index=False))

print("\n--- the base arm only, gross vs net, per market ------------------------------------")
bb = D[D.arm == "base"][["market", "block", "n", "gross", "cost_atr", "net", "gross_pf", "net_pf"]]
print(bb.round(4).to_string(index=False))
print("\n    A market that is gross-POSITIVE and net-negative has a cost problem; one that is")
print("    gross-negative has a signal problem, and no execution improvement reaches it.")

C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
D.to_csv(f"{C}/x9_gross.csv", index=False)
print(f"\n    wrote {C}/x9_gross.csv")
