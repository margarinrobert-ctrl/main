"""What the model actually uses, attributed by SOURCE FRAME rather than by column prefix.

`v22vol.build` owns the `vol.` prefix for 71 VOLATILITY columns and the flow module's volume-level
family was originally prefixed the same way, so a prefix-grouped importance table attributed the
volatility family's weight to volume. Columns are grouped here by which frame they came from --
FLOW (the 43 new columns) against BASE (V28's 141) -- and only then by family inside it.

Research block only. `STUDY_FEATURES` found that ranking feature importance over BOTH blocks
produced a family that failed research (p 0.08) and "passed" locked (p 0.02).

Usage: python3 research/v32/v32imp.py
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "research/v32")
import v32run as V            # noqa: E402


def report(market, tf=30):
    Xf, Xb, R, meta = V.build(market, tf, 1)
    sess = meta["sess"][meta["ok"]]
    res, _lk = V.blocks(sess)
    ri = np.flatnonzero(res)
    X = pd.concat([Xf, Xb], axis=1)
    src = pd.Series(["FLOW"] * Xf.shape[1] + ["BASE"] * Xb.shape[1], index=X.columns)
    m = V.make("lgbm", "R")
    m.fit(X.iloc[ri], R[ri])
    imp = pd.Series(m.feature_importances_, index=X.columns, dtype=float)
    tot = imp.sum()

    V.hdr(f"{market} {tf}m   FEATURE IMPORTANCE, research block only, LightGBM trained on R"
          f"   ({Xf.shape[1]} FLOW + {Xb.shape[1]} BASE columns)")
    by_src = imp.groupby(src).sum()
    print("   by SOURCE FRAME:  " + "   ".join(
        f"{k} {v / tot:.1%} over {int((src == k).sum())} columns "
        f"({v / tot / ((src == k).sum() / len(src)):.2f}x its column share)"
        for k, v in by_src.sort_values(ascending=False).items()))
    fam = imp.groupby([f"{src[c]}:{c.split('.')[0]}" for c in imp.index]).sum()
    print("   by FAMILY:        " + "   ".join(f"{k} {v / tot:.1%}"
                                               for k, v in fam.sort_values(ascending=False).items()))
    print("\n   top 15 FLOW columns")
    for k, v in imp[src == "FLOW"].sort_values(ascending=False).head(15).items():
        print(f"      {k:<30}{v:>8.0f}{v / tot:>9.2%}")
    print("   top 10 BASE columns")
    for k, v in imp[src == "BASE"].sort_values(ascending=False).head(10).items():
        print(f"      {k:<30}{v:>8.0f}{v / tot:>9.2%}")


if __name__ == "__main__":
    for mkt in ("NQ", "US30"):
        report(mkt, 30)
