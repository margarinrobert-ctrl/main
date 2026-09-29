"""The sweep: every configuration, both halves stored, nothing read here."""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import m_core as M

t0 = time.time()
B = M.Base()
pairs = M.length_pairs()
cbs = np.array([max(1, int(round(c / M.TF))) for c in M.CROSS], np.int64)
m = len(B.side)
n_pairs = len(M.TYPES) ** 2 * len(pairs)
NCFG = n_pairs * 48
print(f"{len(M.TYPES)}x{len(M.TYPES)} types x {len(pairs)} length pairs x 16 gates x 3 exits = {NCFG:,} configurations")
lens = sorted(set(M.FAST) | set(M.SLOW))
for k in M.TYPES:                                  # warm the MA cache: 7 x 43 full-series averages
    for n in lens:
        B.ma(k, n)
print(f"MA cache: {len(B._cache)} series in {time.time()-t0:.0f}s")

out = np.zeros((NCFG, 12), np.float32); hsh = np.zeros(NCFG, np.uint64)
meta = np.zeros((n_pairs, 4), np.int16)           # fast type, slow type, fast len, slow len
ageU = np.zeros(m, np.int64); ageD = np.zeros(m, np.int64); stS = np.zeros(m, np.bool_)
xbO = np.zeros((3, m), np.int64); ptsO = np.zeros((3, m))
buf = np.zeros((48, 12)); hb = np.zeros(48, np.uint64)
pid = 0
for i, kf in enumerate(M.TYPES):
    for j, ks in enumerate(M.TYPES):
        for nf, ns in pairs:
            M.pair_kernel(B.ma(kf, nf), B.ma(ks, ns), B.seg_lo, B.seg_sig, B.seg_hi, B.side, B.R,
                          B.o, B.ent, B.xb, B.pts, B.cost, ageU, ageD, stS, xbO, ptsO)
            M.config_kernel(B.sig, B.side, B.is_res, B.ent, ageU, ageD, stS, xbO, ptsO, cbs, buf, hb, 0)
            out[pid * 48:(pid + 1) * 48] = buf; hsh[pid * 48:(pid + 1) * 48] = hb
            meta[pid] = (i, j, nf, ns); pid += 1
        print(f"  fast {kf:6s} x slow {ks:6s} done  ({pid*48:,} configs, {time.time()-t0:.0f}s)", flush=True) if j == 6 else None
np.savez_compressed(os.path.join(HERE, "s1_sweep.npz"), out=out, hsh=hsh, meta=meta,
                    types=np.array(M.TYPES), gates=np.array(M.GATES), exits=np.array(M.EXITS))
print(f"saved {NCFG:,} rows in {time.time()-t0:.0f}s")
