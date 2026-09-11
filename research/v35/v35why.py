"""Why the direction model scores AUC 0.86, and why that number is worth nothing.

A booster reading 25 window-shape features predicts WHICH SIDE BREAKS FIRST at AUC 0.86 on a 0.495
base rate. That is far too high for a market prediction, so the first question is not "what did it
find" but "what is it reading". The candidate is trivial and mechanical:

    f_close_pos -- where the window CLOSED inside its own range.

If the window closes at the top of its range, the high is a few ticks away and the low is a full
range away. The high therefore breaks first almost by construction. That is a real causal
relationship and it is worth nothing to trade, because the level being broken is already touching
price: there is no room between the entry and the barrier.

This module measures that directly. `f_close_pos` alone against the same label, then the model with
it removed, then the DISTANCE-to-each-edge stated explicitly. If the AUC collapses when position
is removed, the model was reading geometry, not the auction.
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "research")
sys.path.insert(0, "research/v35")
import v35bal as B            # noqa: E402
import v35ml as M             # noqa: E402


def main():
    d = B.bars(B.TF)
    T = B.outcomes(d, B.window_table(d, 570, 60))
    res, _l = B.blocks(d["sess"])
    X, T, cols = M.feats(T)
    m = T.sess.isin(np.unique(d["sess"][res])).to_numpy() & (T.brk != 0).to_numpy()
    X, T = X[m].reset_index(drop=True), T[m].reset_index(drop=True)
    y = (T.brk > 0).astype(int).to_numpy()

    print("=" * 118)
    print("WHY THE DIRECTION MODEL SCORES 0.86 -- and why it is worth nothing")
    print("=" * 118)
    print(f"   {len(y)} research sessions, base rate up {y.mean():.3f}")

    print("\n   1. SINGLE FEATURES, alone, against the same label")
    for f in ("f_close_pos", "f_vwap_pos", "f_body", "f_dir", "f_upwick", "f_dnwick",
              "f_hi_when", "f_lo_when", "f_rng_atr", "f_vol_bal"):
        if f in X.columns:
            print(f"      {f:<16} AUC {M.auc(y, X[f].to_numpy()):.4f}")

    print("\n   2. THE GEOMETRY STATED EXPLICITLY -- distance from the window close to each edge")
    to_hi = (T.w_hi - (T.w_lo + T.f_close_pos * T.rng)) / T.atr
    to_lo = ((T.w_lo + T.f_close_pos * T.rng) - T.w_lo) / T.atr
    nearer = (to_lo - to_hi).to_numpy()           # >0 means the HIGH is nearer
    print(f"      'the high is nearer than the low'  AUC {M.auc(y, nearer):.4f}")
    print(f"      share of sessions where the NEARER edge broke first: "
          f"{float(((nearer > 0) == (y == 1)).mean()):.4f}")

    print("\n   3. THE MODEL WITH POSITION FEATURES REMOVED")
    drop = [c for c in X.columns if c in ("f_close_pos", "f_vwap_pos", "f_close_vs_vwap",
                                          "f_body", "f_dir", "f_upwick", "f_dnwick")]
    Xr = X.drop(columns=drop)
    for name in ("xgb", "lgbm"):
        a_full = M.auc(y, M.oof(X, y, name, "dir"))
        a_red = M.auc(y, M.oof(Xr, y, name, "dir"))
        print(f"      {name:<6} full {a_full:.4f}  ->  without the {len(drop)} position features "
              f"{a_red:.4f}   ({a_red - a_full:+.4f})")

    print("\n   4. WHAT THE PREDICTION IS WORTH.  If the model only knows which edge is nearer,")
    print("      the trade it implies has no room: the break level is already at price.")
    near_atr = np.minimum(to_hi.to_numpy(), to_lo.to_numpy())
    print(f"      distance from the window close to the edge that broke, in ATR: "
          f"median {np.median(near_atr):.3f}  mean {near_atr.mean():.3f}")
    R = T.R.to_numpy()
    ok = np.isfinite(R)
    q = pd.qcut(pd.Series(near_atr[ok]), 4, labels=False, duplicates="drop")
    print(f"      break-trade R by distance-to-broken-edge quartile (Q1 = nearest):")
    for i in range(int(q.max()) + 1):
        s = R[ok][q == i]
        print(f"         Q{i + 1}  n {len(s):>4}  mean R {s.mean():>+8.4f}  "
              f"PF {s[s > 0].sum() / abs(s[s < 0].sum()):>6.3f}")


if __name__ == "__main__":
    main()
