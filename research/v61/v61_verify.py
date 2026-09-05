"""Transcription check: the V61 tensor against `v56core.walk` on identical signal bars.

A cached tensor that walks each (bar, geometry) once is only worth having if it agrees
trade-for-trade with the walker the published result came from. `STUDY_V14` caught its own tensor
indexing an exit channel one bar staler than `eem.run` -- the TRADE COUNT matched exactly and the
net did not, which is why both are checked here.
"""
from __future__ import annotations
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v61core as V
sys.path.insert(0, "research/v56")
import v56core as K


def main():
    for tf in V.TFS:
        D = V.build(tf)
        res = V.run_tf(D)
        Gd, rows = res["G"], res["rows"]
        bad = 0
        for _, g in Gd.sample(8, random_state=0).iterrows():
            gi = int(g.name)
            if g["adapt"]:
                continue                      # v56core has no adaptive stop to compare against
            exlo = D["ex_lo"][int(g["exN"])]
            xb2, R2, _ = K.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64),
                                exlo, float(g["stop"]), float(g["tp"]), V.COST, V.SLIP,
                                int(g["hold"]), 0)
            x1, r1 = res["xb"][:, gi], res["R"][:, gi]
            ok = (xb2 >= 0) & np.isfinite(R2) & (x1 >= 0) & np.isfinite(r1)
            dx = int((x1[ok] != xb2[ok]).sum())
            dr = float(np.max(np.abs(r1[ok] - R2[ok]))) if ok.any() else 0.0
            bad += dx + int(dr > 1e-4)
            print(f"  tf {tf:2d}  exN {int(g['exN']):2d} stop {g['stop']:.1f} tp {g['tp']:.0f} "
                  f"hold {int(g['hold']):3d}   n {int(ok.sum()):5d}  exit-bar mismatches {dx}  "
                  f"max |dR| {dr:.2e}")
        print(f"  tf {tf}: {'IDENTICAL' if bad == 0 else str(bad) + ' DISAGREEMENTS'}\n")


if __name__ == "__main__":
    main()
