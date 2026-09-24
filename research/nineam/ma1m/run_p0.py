"""PARITY FIRST: the fast engine against Ctx30.trades on randomly drawn configurations.

Nothing from the million-configuration sweep is read unless this passes: every drawn config must
reproduce the research engine's trade COUNT exactly and its total points to rounding, on both
halves. Mixed-type pairs are included (a Ctx30 is handed the pair's state/age/cross arrays through
`signal_state`, whose faithfulness to na_core.ema_state / cross_exit is asserted first on
same-type pairs).
"""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import m_core as M
import na_core as N

t0 = time.time()
B = M.Base()
print(f"base built in {time.time()-t0:.1f}s: {len(B.sig)} breaks on {len(np.unique(B.c.day[B.sig]))} sessions, "
      f"{len(B.R):,} segment rows; research {int(B.is_res.sum())} / holdout {int((~B.is_res).sum())} breaks")
print(f"natural exits: {dict(zip(*np.unique(B.why, return_counts=True)))}  (1 stop/ratchet, 2 target, 3 flatten)")

# 1. signal_state reproduces na_core on same-type pairs
for kind, a, b in [("ema", 13, 48), ("sma", 9, 21), ("hull", 21, 55), ("linreg", 13, 48), ("tema", 5, 30)]:
    st0, u0, d0 = N.ema_state(B.f, a, b, kind)
    cc0 = N.cross_exit(B.f, a, b, kind, "cross"); cs0 = N.cross_exit(B.f, a, b, kind, "state")
    st1, u1, d1, cc1, cs1 = M.signal_state(N.ma(B.close, a, kind), N.ma(B.close, b, kind))
    same = (np.array_equal(st0, st1) and np.array_equal(u0, u1) and np.array_equal(d0, d1)
            and np.array_equal(cc0, cc1) and np.array_equal(cs0, cs1))
    assert same, f"signal_state diverges from na_core on {kind} {a}/{b}"
print("signal_state == na_core.ema_state + cross_exit on 5 same-type pairs: asserted")

# 2. the kernels against Ctx30.trades
rng = np.random.default_rng(2026)
pairs = M.length_pairs()
cbs = np.array([max(1, int(round(c / M.TF))) for c in M.CROSS], np.int64)
m = len(B.side)
ok = 0; tested = 0; worst = 0.0
for trial in range(120):
    kf, ks = M.TYPES[rng.integers(7)], M.TYPES[rng.integers(7)]
    nf, ns = pairs[rng.integers(len(pairs))]
    a = B.ma(kf, nf); b = B.ma(ks, ns)
    ageU = np.zeros(m, np.int64); ageD = np.zeros(m, np.int64); stS = np.zeros(m, np.bool_)
    xbO = np.zeros((3, m), np.int64); ptsO = np.zeros((3, m))
    M.pair_kernel(a, b, B.seg_lo, B.seg_sig, B.seg_hi, B.side, B.R, B.o, B.ent, B.xb, B.pts,
                  B.cost, ageU, ageD, stS, xbO, ptsO)
    out = np.zeros((48, 12)); hsh = np.zeros(48, np.uint64)
    M.config_kernel(B.sig, B.side, B.is_res, B.ent, ageU, ageD, stS, xbO, ptsO, cbs, out, hsh, 0)
    c = M.ctx_for(B, kf, nf, ks, ns)
    for _ in range(3):
        g = int(rng.integers(len(M.GATES))); x = int(rng.integers(3))
        tr = c.trades(M.cfg_dict(g, x))
        row = out[g * 3 + x]
        if tr is None or len(tr) == 0:
            eng_n = (0, 0); eng_s = (0.0, 0.0)
        else:
            r = np.isin(tr["eday"].to_numpy(), B.res_days)
            eng_n = (int(r.sum()), int((~r).sum()))
            eng_s = (float(tr.pct[r].sum()), float(tr.pct[~r].sum()))
        fast_n = (int(row[0]), int(row[6])); fast_s = (row[1], row[7])
        d = max(abs(eng_s[0] - fast_s[0]), abs(eng_s[1] - fast_s[1]))
        worst = max(worst, d); tested += 1
        if eng_n == fast_n and d < 1e-9:
            ok += 1
        else:
            print(f"  MISMATCH {kf}{nf}/{ks}{ns} {M.GATES[g]} exit={M.EXITS[x]}: engine n {eng_n} sum {eng_s} "
                  f"| fast n {fast_n} sum {fast_s}")
print(f"\nPARITY: {ok} of {tested} random configurations identical (count exact, max |d sum %| {worst:.2e})")
print(f"elapsed {time.time()-t0:.1f}s")
