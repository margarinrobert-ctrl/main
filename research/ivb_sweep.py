"""A full parameter search over IVB, on the engine with the look-ahead removed.

The published IVB result was a bug (see the retraction in docs/ib/STUDY_IVB.md). This asks the
honest question: with the trend filter reading only bars that closed before the session opened,
is there ANY configuration of Initial Value Breakout worth trading?

Chosen on the research block, read once on the locked block, as everywhere else.
"""
from __future__ import annotations

import sys
import time

import numpy as np
from numba import njit, prange

sys.path.insert(0, "research")
from bos_choch import prep
from ivb import session_context, run

TFS = [5, 15, 30]
IVMIN = [15, 30, 60, 90]
USE_IB = [1, 0]                 # opening high/low, or the opening value area
ENTRY = [0, 1, 2, 3]            # break / retest / halfway retest / failed-break fade
STOP = [0, 1, 2, 3]             # ATR / opposite edge / midpoint / trigger-bar extreme
ATRM = [1.0, 2.0]
TGTM = [0, 1]                   # R multiple, or a multiple of the initial range
TP = [1.0, 1.5, 2.0]
BUF = [0.0, 0.15]
TREND = [0, 1, 2]               # off / must agree / must disagree
RNGF = [0, 1]
FLAT = [900, 960]
SIDE = [0, 1, -1]


@njit(parallel=True, cache=True)
def sweep(o, h, l, c, mod, sidx, atr_, vah, val, poc, ivh, ivl, pct, trend,
          iv_min, G, cut_idx, out, base):
    for j in prange(G.shape[0]):
        run(o, h, l, c, mod, sidx, atr_, vah, val, poc, ivh, ivl, pct, trend,
            iv_min, np.int64(G[j, 0]), np.int64(G[j, 1]), np.int64(G[j, 2]), G[j, 3],
            np.int64(G[j, 4]), G[j, 5], G[j, 6], np.int64(G[j, 7]), np.int64(G[j, 8]),
            G[j, 9], np.int64(G[j, 10]), cut_idx, out, base + j)


def grid():
    rows = []
    for ib in USE_IB:
        for e in ENTRY:
            for st in STOP:
                for am in ATRM:
                    for tm in TGTM:
                        for tp in TP:
                            for bf in BUF:
                                for tr in TREND:
                                    for rf in RNGF:
                                        for fl in FLAT:
                                            for sd in SIDE:
                                                rows.append((ib, e, st, am, tm, tp, bf,
                                                             tr, rf, fl, sd))
    return np.array(rows, np.float64)


def main():
    t0 = time.time()
    G = grid()
    preps = [(tf, iv) for tf in TFS for iv in IVMIN]
    total = len(preps) * len(G)
    print(f"{len(preps)} data preparations x {len(G):,} parameter sets = {total:,} configurations")
    out = np.zeros((total, 20))
    meta = np.zeros((total, 2))
    row = 0
    for tf, iv in preps:
        d = prep(tf)
        us, poc, vah, val, ivh, ivl, pct, trend = session_context(iv)
        idx = {s: i for i, s in enumerate(us)}
        sidx = np.array([idx.get(s, -1) for s in d["sess"]], np.int64)
        cut = np.int64(int(0.65 * len(us)))
        sweep(d["o"], d["h"], d["l"], d["c"], d["mod"].astype(np.int64), sidx, d["atr"],
              vah, val, poc, ivh, ivl, pct, trend, iv, G, cut, out, row)
        meta[row:row + len(G)] = (tf, iv)
        row += len(G)
        print(f"   {tf:>3}m bars, {iv:>3}m initial value   {row:>9,} rows   "
              f"{time.time()-t0:6.1f}s", flush=True)
    np.save("results/ivb/ivb_out.npy", out)
    np.save("results/ivb/ivb_meta.npy", meta)
    np.save("results/ivb/ivb_grid.npy", G)
    print(f"\ndone in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
