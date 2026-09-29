"""An independent discovery cycle on US100 -- nothing selected on NQ influences it.

The split is CHRONOLOGICAL and deliberately backwards from convenience: the research block is
2016-11 to 2021-12, six years no rule in this repository has ever touched, and the holdout is
2022-01 onward. Anything that survives is then checked on NQ as a third, different-instrument
test.

Reuses `alpha_factory2`'s bit-packed sweep kernel and `alpha_ladder`'s 198-condition pool, both
pointed at `us100.to_bars`. The multiplicity is stated before any number is read.
"""
from __future__ import annotations

import sys, time
from itertools import combinations

import numpy as np

sys.path.insert(0, "research")
import us100
from alpha_factory2 import price_one, sweep
from alpha_ladder import build_ladder

# CLAUDE.md: "Ban calendar conditions from rule search. Weekday and month conditions partition the
# sample five or twelve ways and hand the search a free lottery. Removing them was worth $8,771 on
# the holdout." The first run of this module did NOT exclude them and the damage was immediately
# visible: "Fri" appeared 878 times in the top 10,000 by research, and the sixth-best rule overall
# (outside bar AND last hour AND Fri) made $90.0/trade on research and LOST $110.9 on the holdout.
CALENDAR = {"Mon", "Tue", "Wed", "Thu", "Fri", "first half of month", "month end (last 3d)"}

# a deliberately small geometry set -- the point of this run is CONDITIONS, and every extra
# geometry multiplies the multiplicity that every p-value here has to pay for
EXITS = [(2.0, 1.0, 960), (3.0, 1.0, 960), (4.0, 1.0, 960), (2.5, 1.0, 0)]
SPLIT = "2022-01-01"


def run(tf=30, max_k=3, out="results/us100/us100_search.npz"):
    t0 = time.time()
    d = us100.to_bars(tf)
    names, M = build_ladder(d)
    M = np.asarray(M)
    keep = [i for i, n in enumerate(names) if str(n) not in CALENDAR]
    dropped = len(names) - len(keep)
    names = [names[i] for i in keep]; M = M[keep]
    print(f"dropped {dropped} calendar conditions before searching")
    nbars = M.shape[1]
    idx = d["df"].index
    print(f"{len(names)} conditions on {nbars:,} US100 {tf}m bars")

    combos = [(i, -1, -1) for i in range(len(names))]
    if max_k >= 2:
        combos += [(a, b, -1) for a, b in combinations(range(len(names)), 2)]
    if max_k >= 3:
        combos += [(a, b, c) for a, b, c in combinations(range(len(names)), 3)]
    combos = np.array(combos, np.int32)
    variants = [(s, gi) for s in (1, -1) for gi in range(len(EXITS))]
    total = len(combos) * len(variants)
    print(f"{len(combos):,} rules x {len(variants)} variants = {total:,} strategies")
    print(f"Bonferroni threshold for ONE claim at this multiplicity: p < {0.05/total:.2g}")

    nw = (nbars + 63) // 64
    B = np.zeros((len(names), nw), np.uint64)
    for i in range(len(names)):
        for p in np.flatnonzero(M[i]):
            B[i, p >> 6] |= np.uint64(1) << np.uint64(p & 63)

    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us_, sidx = np.unique(d["sess"], return_inverse=True)
    sidx = sidx.astype(np.int64)
    # the cut is a DATE, not a fraction: research is the six years nothing here has seen
    cut = np.int64(int(np.searchsorted(us_, d["sess"][idx >= np.datetime64(SPLIT)][0])))
    print(f"research = bars before {SPLIT} ({int((idx < np.datetime64(SPLIT)).sum()):,}), "
          f"holdout = {int((idx >= np.datetime64(SPLIT)).sum()):,}")

    EB = np.zeros((len(variants), nbars), np.int64)
    EP = np.zeros((len(variants), nbars), np.float64)
    OK = np.zeros((len(variants), nbars), np.int64)
    for vi, (s, gi) in enumerate(variants):
        am, tp, fl = EXITS[gi]
        price_one(o, h, l, c, atr_, mod, s, am, tp, fl, EB[vi], EP[vi], OK[vi])
    print(f"  exits priced, {time.time()-t0:.0f}s", flush=True)

    rn = np.zeros(total, np.float32); ln = np.zeros(total, np.float32)
    rc = np.zeros(total, np.int32); lc = np.zeros(total, np.int32)
    sweep(B, combos, nbars, EB, EP, OK, sidx, cut, rn, rc, ln, lc)
    print(f"  sweep done, {time.time()-t0:.0f}s", flush=True)
    np.savez_compressed(out, res_net=rn, res_n=rc, lok_net=ln, lok_n=lc,
                        combos=combos, names=np.array(names),
                        exits=np.array(EXITS), variants=np.array(variants), tf=np.array([tf]))
    print(f"saved {out}, total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
