"""Every 1R strategy in the generator's space, ranked by win rate -- with the bound in view.

At a 1R target a driftless path wins 50% of the time. That is the number a 1R win rate has to
beat, and it is why 60% is a real bar rather than a cosmetic one: +10 points of excess at 1:1 is
the same quality of edge as 43.3% at 2:1 or 35% at 3:1.

The sweep stores what pass 1 of alpha_factory2 never did -- the WIN COUNT per block -- because
"win rate" cannot be recovered from net P&L and trade count. A win here is a trade that finished
positive AFTER costs, which at a 1.0xATR stop is a meaningfully stricter definition than "the
target was touched first".
"""
from __future__ import annotations

import sys
import time
from itertools import combinations

import numpy as np
from numba import njit, prange

sys.path.insert(0, "research")
from alpha_factory2 import build_conditions, price_one
from bos_choch import prep

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK

ATR_MULTS = [1.0, 1.5, 2.0, 2.5]
FLATS = [0, 960]
EXITS_1R = [(a, 1.0, f) for a in ATR_MULTS for f in FLATS]


@njit(parallel=True, cache=True)
def sweep_wins(B, combos, nbars, EB, EP, OK, sidx, cut,
               r_n, r_sum, r_win, l_n, l_sum, l_win):
    nw = B.shape[1]
    nvar = EB.shape[0]
    for r in prange(combos.shape[0]):
        i0 = combos[r, 0]; i1 = combos[r, 1]; i2 = combos[r, 2]
        trig = np.empty(nbars, np.int32)
        nt = 0
        for w in range(nw):
            word = B[i0, w]
            if i1 >= 0:
                word &= B[i1, w]
            if i2 >= 0:
                word &= B[i2, w]
            if word == np.uint64(0):
                continue
            base = w * 64
            for b in range(64):
                if (word >> np.uint64(b)) & np.uint64(1):
                    p = base + b
                    if p < nbars:
                        trig[nt] = p; nt += 1
        for vv in range(nvar):
            free = -1
            rn = 0; rs = 0.0; rw = 0; ln = 0; ls = 0.0; lw = 0
            for t in range(nt):
                i = trig[t]
                if i < free or OK[vv, i] == 0:
                    continue
                free = EB[vv, i]
                p = EP[vv, i]
                if sidx[i] < cut:
                    rn += 1; rs += p
                    if p > 0.0:
                        rw += 1
                else:
                    ln += 1; ls += p
                    if p > 0.0:
                        lw += 1
            k = r * nvar + vv
            r_n[k] = rn; r_sum[k] = rs; r_win[k] = rw
            l_n[k] = ln; l_sum[k] = ls; l_win[k] = lw


def main(tf=30, out=None):
    t0 = time.time()
    d = prep(tf)
    names, M = build_conditions(d)
    nbars = M.shape[1]
    combos = [(i, -1, -1) for i in range(len(names))]
    combos += [(a, b, -1) for a, b in combinations(range(len(names)), 2)]
    combos += list(combinations(range(len(names)), 3))
    combos = np.array(combos, np.int32)
    variants = [(s, gi) for s in (1, -1) for gi in range(len(EXITS_1R))]
    total = len(combos) * len(variants)
    print(f"{tf}m: {len(combos):,} rules x {len(variants)} 1R variants = {total:,} strategies",
          flush=True)

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
        am, tp, fl = EXITS_1R[gi]
        price_one(o, h, l, c, atr_, mod, s, am, tp, fl, EB[vi], EP[vi], OK[vi])
    print(f"   exits precomputed, {time.time()-t0:.0f}s", flush=True)

    z = lambda dt: np.zeros(total, dt)
    r_n, r_win, l_n, l_win = z(np.int32), z(np.int32), z(np.int32), z(np.int32)
    r_sum, l_sum = z(np.float32), z(np.float32)
    sweep_wins(B, combos, nbars, EB, EP, OK, sidx, cut, r_n, r_sum, r_win, l_n, l_sum, l_win)
    print(f"   swept, {time.time()-t0:.0f}s", flush=True)

    path = out or f"results/oner/oner_{tf}m.npz"
    np.savez_compressed(path, r_n=r_n, r_sum=r_sum, r_win=r_win, l_n=l_n, l_sum=l_sum,
                        l_win=l_win, combos=combos, names=np.array(names),
                        exits=np.array(EXITS_1R), tf=np.array([tf]))
    print(f"saved {path}, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    for _tf in ([int(x) for x in sys.argv[1:]] or [30]):
        main(_tf)
