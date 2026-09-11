"""PHASE 1 -- generate. Every 1R strategy across an expanded geometry space.

    253,575 rules x 6 stop widths x 3 flatten times x 2 directions = 9,128,700 per timeframe
    x 3 timeframes                                                 = 27,386,100 combinations

Win counts are stored per block, because a win rate cannot be recovered from net P&L and trade
count, and the whole point of a 1R search is the win rate.

Phase 1 keeps only what survives a minimal bar -- enough trades in both blocks and profitable on
research -- because 27 million rows of everything is 650 MB of mostly noise. The gates that
matter (calendar ban, base-rate excess, subset coherence) are Phase 2's job.
"""
from __future__ import annotations

import sys
import time
from itertools import combinations

import numpy as np

sys.path.insert(0, "research")
from alpha_factory2 import build_conditions, price_one
from bos_choch import prep
from oner_hunt import sweep_wins

STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
FLATS = [0, 900, 960]
EXITS = [(a, 1.0, f) for a in STOPS for f in FLATS]
MIN_RES, MIN_LOK = 50, 20


def main(tf, out=None):
    t0 = time.time()
    d = prep(tf)
    names, M = build_conditions(d)
    nbars = M.shape[1]
    combos = [(i, -1, -1) for i in range(len(names))]
    combos += [(a, b, -1) for a, b in combinations(range(len(names)), 2)]
    combos += list(combinations(range(len(names)), 3))
    combos = np.array(combos, np.int32)
    variants = [(s, gi) for s in (1, -1) for gi in range(len(EXITS))]
    total = len(combos) * len(variants)
    print(f"  {tf}m: {len(combos):,} rules x {len(variants)} variants = {total:,}", flush=True)

    nw = (nbars + 63) // 64
    B = np.zeros((len(names), nw), np.uint64)
    for i in range(len(names)):
        for p in np.flatnonzero(M[i]):
            B[i, p >> 6] |= np.uint64(1) << np.uint64(p & 63)

    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us = np.unique(d["sess"]); sidx = np.searchsorted(us, d["sess"]).astype(np.int64)
    cut = np.int64(int(0.65 * len(us)))

    EB = np.zeros((len(variants), nbars), np.int64)
    EP = np.zeros((len(variants), nbars), np.float64)
    OK = np.zeros((len(variants), nbars), np.int64)
    for vi, (s, gi) in enumerate(variants):
        am, tp, fl = EXITS[gi]
        price_one(o, h, l, c, atr_, mod, s, am, tp, fl, EB[vi], EP[vi], OK[vi])
    print(f"     exits precomputed {time.time()-t0:.0f}s", flush=True)

    z = lambda t: np.zeros(total, t)
    r_n, r_win, l_n, l_win = z(np.int32), z(np.int32), z(np.int32), z(np.int32)
    r_sum, l_sum = z(np.float32), z(np.float32)
    sweep_wins(B, combos, nbars, EB, EP, OK, sidx, cut, r_n, r_sum, r_win, l_n, l_sum, l_win)
    print(f"     swept {time.time()-t0:.0f}s", flush=True)

    live = (r_n >= MIN_RES) & (l_n >= MIN_LOK) & (r_sum > 0)
    keep = np.flatnonzero(live)
    print(f"     {len(keep):,} of {total:,} ({100*len(keep)/total:.2f}%) have "
          f"{MIN_RES}+/{MIN_LOK}+ trades and are research-profitable", flush=True)
    path = out or f"results/oner/mega_{tf}m.npz"
    np.savez_compressed(path, idx=keep.astype(np.int64),
                        r_n=r_n[keep], r_sum=r_sum[keep], r_win=r_win[keep],
                        l_n=l_n[keep], l_sum=l_sum[keep], l_win=l_win[keep],
                        base_rn=r_n, base_rw=r_win,          # for the population base rate
                        combos=combos, names=np.array(names), exits=np.array(EXITS),
                        nvar=np.array([len(variants)]), tf=np.array([tf]),
                        total=np.array([total]))
    print(f"     saved {path}, {time.time()-t0:.0f}s\n", flush=True)
    return len(keep), total


if __name__ == "__main__":
    tfs = [int(x) for x in sys.argv[1:]] or [15, 30, 60]
    tk = tt = 0
    print("PHASE 1 -- GENERATE")
    for tf in tfs:
        k, t = main(tf)
        tk += k; tt += t
    print(f"PHASE 1 DONE: {tt:,} combinations generated, {tk:,} survive the minimal bar")
