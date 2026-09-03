"""V63 parity -- the shipped script's own order model against the engine.

The two differ in exactly one place, and it is worth measuring rather than assuming: the engine
closes a time-capped trade at the CLOSE of the cap bar, and `strategy.close_all()` cannot sell the
close of the bar that triggers it -- it fills at the NEXT bar's OPEN. The stop is identical in both,
because the script places a FILL-RELATIVE bracket at the signal bar (the V56 parity fix), so a stop
is live during the entry bar and is anchored to the signal bar's ATR, which is what the engine uses.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V                                     # noqa: E402
from run_v63b import res_for, set_rows                  # noqa: E402
from run_v63d import FINAL                              # noqa: E402


@njit(cache=True)
def _walk(o, h, l, c, atr, rows, stop, cost, slip, hold, m, pine):
    n = len(rows)
    xb = np.full(n, -1, np.int64)
    pts = np.full(n, np.nan)
    for k in range(n):
        i = rows[k]
        a = i + 1
        anc = atr[i]
        if a < 2 or a >= m - 3 or not np.isfinite(anc) or anc <= 0:
            continue
        px = o[a] + slip
        lvl = px - stop * anc
        end = a + hold
        if end > m - 3:
            end = m - 3
        out = np.nan
        j = a
        while j <= end:
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip
                break
            j += 1
        if not np.isfinite(out):
            if pine == 1:
                j = end + 1
                out = o[j] - slip          # close_all fills at the NEXT bar's open
            else:
                j = end
                out = c[j] - slip
        xb[k] = j
        pts[k] = out - px - cost
    return xb, pts


def main():
    print(__doc__)
    for m in V.FEEDSORDER:
        res = res_for(m, int(FINAL["tf"]))
        D = res["D"]
        sel, _ = set_rows(res, FINAL)
        rows = res["rows"][sel]
        out = {}
        for pine in (0, 1):
            xb, pts = _walk(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64),
                            float(FINAL["stop"]), D["cost"], D["slip"], 480, D["n"], pine)
            free, keep = -1, []
            for j in range(len(rows)):
                if xb[j] < 0 or not np.isfinite(pts[j]) or rows[j] <= free:
                    continue
                free = xb[j]
                keep.append(j)
            k = np.asarray(keep, np.int64)
            out[pine] = (rows[k], xb[k], 100.0 * pts[k] / D["o"][rows[k] + 1])
        eb, ex, ep = out[0]
        pb, px_, pp = out[1]
        common, ie, ip = np.intersect1d(eb, pb, return_indices=True)
        same = float(np.mean(ex[ie] == px_[ip]))
        corr = float(np.corrcoef(ep[ie], pp[ip])[0, 1])
        gap = 100.0 * (pp[ip].mean() - ep[ie].mean()) / abs(ep[ie].mean())
        print(f"  {m:7s} engine {len(eb)} trades, script {len(pb)}, shared {len(common)}   "
              f"identical exit bar {100*same:.2f}%   correlation {corr:.4f}")
        print(f"  {'':7s} engine {ep[ie].mean():+.4f} %/trade   script {pp[ip].mean():+.4f}   "
              f"gap {gap:+.1f}%")


if __name__ == "__main__":
    main()
