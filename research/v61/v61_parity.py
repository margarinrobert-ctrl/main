"""V61 parity -- the two presets under the SCRIPT's order model against the research engine.

`STUDY_PINE_PARITY` and `STUDY_V56_PARITY_ADX_TP` are unambiguous: a Pine port cannot be asserted
by reading it. `v56core.walk(pine=2)` is the shipped script's own order model -- the exit bracket
is placed at the SIGNAL bar from the signal close so it is live during the fill bar, the risk is
anchored to the SIGNAL bar's ATR, and from the fill onward every level is one bar stale, which is
inherent to Pine and cannot be removed. The number that matters is the GAP.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v56"))
import v61core as V                                     # noqa: E402
import v56core as K                                     # noqa: E402
from run_v61b import tf_data, set_rows                  # noqa: E402

PRESETS = {
    "incumbent   30m  D20/20  2.0N  no target  k3 w20 (90 / 600 min)":
        dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, ma=-99.0, chop=99.0,
             psh=0, cvd="k3w20"),
    "high activity 15m  D15/30  3.0N  6 ATR target  k3 w30 (45 / 450 min)":
        dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=240, adapt=0, ma=-99.0, chop=99.0,
             psh=0, cvd="k3w30"),
}


def series(D, cell, rows, pine):
    xb, R, _ = K.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64),
                      D["ex_lo"][int(cell["exN"])], float(cell["stop"]), float(cell["tp"]),
                      V.COST, V.SLIP, int(cell["hold"]), pine)
    free, keep = -1, []
    for j in range(len(rows)):
        if xb[j] < 0 or not np.isfinite(R[j]) or rows[j] <= free:
            continue
        free = xb[j]
        keep.append(j)
    k = np.asarray(keep, np.int64)
    return rows[k], xb[k], R[k]


def main():
    print(__doc__)
    for name, cell in PRESETS.items():
        D, res = tf_data(cell["tf"])
        sel, _ = set_rows(D, res, cell)
        rows = res["rows"][sel]
        e_b, e_x, e_R = series(D, cell, rows, 0)
        p_b, p_x, p_R = series(D, cell, rows, 2)
        common, ie, ip = np.intersect1d(e_b, p_b, return_indices=True)
        same_exit = float(np.mean(e_x[ie] == p_x[ip])) if len(common) else np.nan
        corr = float(np.corrcoef(e_R[ie], p_R[ip])[0, 1]) if len(common) > 2 else np.nan
        cut = D["cut"]
        print(f"\n  {name}")
        print(f"    engine {len(e_b)} trades   script {len(p_b)} trades   "
              f"count ratio {len(p_b)/max(len(e_b),1):.3f}   shared {len(common)}")
        print(f"    identical exit bar {100*same_exit:.2f}%   R correlation {corr:.4f}")
        for blk, m in (("research", e_b < cut), ("locked", e_b >= cut)):
            mp = p_b < cut if blk == "research" else p_b >= cut
            ge = e_R[m].mean() if m.sum() else np.nan
            gp = p_R[mp].mean() if mp.sum() else np.nan
            gap = 100.0 * (gp - ge) / abs(ge) if np.isfinite(ge) and ge != 0 else np.nan
            print(f"    {blk:9s} engine {ge:+.4f} R on {int(m.sum()):4d}   script {gp:+.4f} R on "
                  f"{int(mp.sum()):4d}   gap {gap:+.1f}%")


if __name__ == "__main__":
    main()
