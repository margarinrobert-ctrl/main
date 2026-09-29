"""PHASE 1 -- generate. Every SAM-anchored scalping rule.

    1,440 SAM conditions
  + 1,440 x 198 SAM AND one ladder condition   =   285,120
  + C(1440, 2) SAM AND another SAM             = 1,036,080
  -------------------------------------------------------
    1,322,640 rules
  x 6 stop widths x 3 flatten times x 2 directions = 47,615,040 per timeframe
  x 3 timeframes (5m, 15m, 30m)                    = 142,845,120 combinations

Every rule contains at least one SAM condition, because the question is what the best SCALPING
version of SAM-Fut is, not what the best rule is -- that search already ran and is recorded in
STUDY_1R_MEGA.md. Ladder conditions enter only as a second leg.

5-minute bars are included and 60-minute are not: a scalp on a 60-minute bar is not a scalp.

Win counts are stored per block, because a win rate cannot be recovered from net P&L and trade
count, and the whole point of a 1R search is the win rate.
"""
from __future__ import annotations

import sys
import time
from itertools import combinations

import numpy as np

sys.path.insert(0, "research")
from alpha_factory2 import price_one
from alpha_ladder import build_ladder
from bos_choch import prep
from oner_hunt import sweep_wins
from sam_pool import conditions as sam_conditions

STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
FLATS = [0, 900, 960]
EXITS = [(a, 1.0, f) for a in STOPS for f in FLATS]
MIN_RES, MIN_LOK = 50, 20


def build_pool(tf):
    """SAM conditions first, then the 198-rung ladder. The split index is what anchors the search."""
    d = prep(tf)
    S = sam_conditions(d, tf)
    sam_names = list(S)
    lad_names, LM = build_ladder(d)
    n = len(d["c"])
    M = np.zeros((len(sam_names) + len(lad_names), n), np.bool_)
    for i, k in enumerate(sam_names):
        M[i] = S[k]
    M[len(sam_names):] = LM
    return d, sam_names, lad_names, M


def enumerate_rules(n_sam, n_lad):
    c = [(i, -1, -1) for i in range(n_sam)]
    c += [(i, n_sam + j, -1) for i in range(n_sam) for j in range(n_lad)]
    c += [(a, b, -1) for a, b in combinations(range(n_sam), 2)]
    return np.array(c, np.int32)


def main(tf, out=None, chunk=None, nchunk=1):
    """`chunk`/`nchunk` sweep a slice of the rule list and save a part file.

    The sweep itself is minutes, but a process that outlives the call that started it gets
    reaped in this environment, so the work is cut into pieces that each finish inside one call
    and `merge()` puts them back together. Nothing about the search changes -- the rule list and
    its order are identical, only the loop is split.
    """
    t0 = time.time()
    import os
    cache = f"results/sam/sambits_{tf}m.npy"
    ncache = f"results/sam/sambits_{tf}m_names.npy"
    if os.path.exists(cache) and os.path.exists(ncache):
        # the bitsets and the name list are all a later chunk needs; rebuilding the boolean
        # condition matrix from 1-minute semivariances is the expensive part and is skipped
        d = prep(tf)
        meta = np.load(ncache, allow_pickle=True)
        names = list(meta[0]); n_sam_cached = int(meta[1])
        sam_names, lad_names = names[:n_sam_cached], names[n_sam_cached:]
        M = None
        nbars = len(d["c"])
    else:
        d, sam_names, lad_names, M = build_pool(tf)
        names = sam_names + lad_names
        nbars = M.shape[1]
        np.save(ncache, np.array([names, len(sam_names)], dtype=object), allow_pickle=True)
    combos_all = enumerate_rules(len(sam_names), len(lad_names))
    if chunk is None:
        combos, lo = combos_all, 0
    else:
        edges = np.linspace(0, len(combos_all), nchunk + 1).astype(np.int64)
        lo, hi = int(edges[chunk]), int(edges[chunk + 1])
        combos = combos_all[lo:hi]
    variants = [(s, gi) for s in (1, -1) for gi in range(len(EXITS))]
    total = len(combos) * len(variants)
    print(f"  {tf}m: {len(sam_names):,} SAM + {len(lad_names)} ladder conditions, "
          f"{len(combos_all):,} rules total"
          + (f", chunk {chunk+1}/{nchunk} = rules {lo:,}..{lo+len(combos):,}" if chunk is not None
             else "")
          + f" -> {total:,} combinations here", flush=True)

    # the bitsets are identical for every chunk of a timeframe, and building them from the
    # 1-minute semivariances is a third of the run time, so they are cached to disk
    if M is None:
        B = np.load(cache)
    else:
        nw = (nbars + 63) // 64
        B = np.zeros((len(names), nw), np.uint64)
        for i in range(len(names)):
            for p in np.flatnonzero(M[i]):
                B[i, p >> 6] |= np.uint64(1) << np.uint64(p & 63)
        del M
        np.save(cache, B)

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
    nv = len(variants)
    path = out or (f"results/sam/sam_{tf}m.npz" if chunk is None
                   else f"results/sam/sampart_{tf}m_{chunk}.npz")
    np.savez(path, idx=(keep + lo * nv).astype(np.int64),      # index into the FULL rule list
             r_n=r_n[keep], r_sum=r_sum[keep], r_win=r_win[keep],
             l_n=l_n[keep], l_sum=l_sum[keep], l_win=l_win[keep],
             base_rn=r_n, base_rw=r_win, lo=np.array([lo]),
             combos=combos_all if chunk is None else np.zeros((0, 3), np.int32),
             names=np.array(names), n_sam=np.array([len(sam_names)]),
             exits=np.array(EXITS), nvar=np.array([nv]), tf=np.array([tf]),
             total=np.array([len(combos_all) * nv]))
    print(f"     saved {path}, {time.time()-t0:.0f}s\n", flush=True)
    return len(keep), total


def merge(tf, nchunk):
    """Stitch the part files back into the single npz the phases expect."""
    d, sam_names, lad_names, _M = build_pool(tf)
    combos = enumerate_rules(len(sam_names), len(lad_names))
    parts = [np.load(f"results/sam/sampart_{tf}m_{k}.npz", allow_pickle=True) for k in range(nchunk)]
    cat = lambda k: np.concatenate([p[k] for p in parts])
    nv = int(parts[0]["nvar"][0])
    np.savez(f"results/sam/sam_{tf}m.npz",
             idx=cat("idx"), r_n=cat("r_n"), r_sum=cat("r_sum"), r_win=cat("r_win"),
             l_n=cat("l_n"), l_sum=cat("l_sum"), l_win=cat("l_win"),
             base_rn=cat("base_rn"), base_rw=cat("base_rw"),
             combos=combos, names=parts[0]["names"], n_sam=parts[0]["n_sam"],
             exits=parts[0]["exits"], nvar=parts[0]["nvar"], tf=parts[0]["tf"],
             total=np.array([len(combos) * nv]))
    print(f"  merged {nchunk} parts -> /tmp/sam_{tf}m.npz  "
          f"({len(cat('idx')):,} surviving combinations of {len(combos)*nv:,})")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "merge":
        merge(int(a[1]), int(a[2]))
    elif len(a) == 3:
        print("PHASE 1 -- GENERATE, SAM-ANCHORED")
        main(int(a[0]), chunk=int(a[1]), nchunk=int(a[2]))
    else:
        tfs = [int(x) for x in a] or [30, 15, 5]
        tk = tt = 0
        print("PHASE 1 -- GENERATE, SAM-ANCHORED")
        for tf in tfs:
            k, t = main(tf)
            tk += k; tt += t
        print(f"PHASE 1 DONE: {tt:,} combinations generated, {tk:,} survive the minimal bar")
