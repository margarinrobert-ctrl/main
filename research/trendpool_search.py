"""The search, with the null that killed the last family moved to the FRONT.

Order of operations, and the order is the point:

  1. sweep every rule x geometry
  2. WINDOW BASELINE gate -- beat what entering at every eligible bar in 07:00-11:00 earns under
     the same side and geometry, on research. This is the cheap version of the matched control.
  3. subset coherence -- every leg must beat the same baseline alone
  4. MATCHED CONTROL ON RESEARCH -- 400 random-entry draws matched on side, geometry and
     minute-of-day. Last time this was run only at the end, after the holdout; it rejected
     everything, and four rules had already been carried to a holdout they then "passed". Running
     it on research first means nothing reaches the holdout that has not already beaten a random
     long at the same times.
  5. only then the locked block, once

Usage: python3 research/trendpool_search.py [tf ...]
"""
from __future__ import annotations

import sys
from itertools import combinations, product

import numpy as np

sys.path.insert(0, "research")
from alpha_factory2 import price_one
from oner_hunt import sweep_wins
from trendpool import EXITS, WINDOW, pool

MIN_RES, MIN_LOK = 30, 12


def enumerate_rules(ns, npb, nrs):
    a, b, c = (list(range(ns)), list(range(ns, ns + npb)),
               list(range(ns + npb, ns + npb + nrs)))
    r = [(i, -1, -1) for i in a + b + c]
    r += [(i, j, -1) for i, j in combinations(a + b + c, 2)]
    r += [(i, j, k) for i, j, k in product(a, b, c)]
    return np.array(r, np.int32)


def window_baseline(d, side, win, verbose=False):
    """What entering at EVERY eligible bar in the window earns, per geometry, on research."""
    from oner_union import _cut, _sim
    si, cut, _ = _cut(d)
    trig = np.flatnonzero(win).astype(np.int64)
    out = {}
    for vi, (am, tp, fl) in enumerate(EXITS):
        pnl, eb, *_ = _sim(d, trig, side, am, fl)
        m = si[eb] < cut
        out[vi] = (100.0 * float((pnl[m] > 0).mean()) if m.sum() else np.nan,
                   float(pnl[m].mean()) if m.sum() else np.nan)
    return out


def sweep_side(tf, side, verbose=True):
    d, names, M, (ns, npb, nrs), win = pool(tf, side)
    M[ns + npb:] &= win                      # the resumption is the order bar
    nbars = M.shape[1]
    combos = enumerate_rules(ns, npb, nrs)
    nw = (nbars + 63) // 64
    B = np.zeros((len(names), nw), np.uint64)
    for i in range(len(names)):
        for p in np.flatnonzero(M[i]):
            B[i, p >> 6] |= np.uint64(1) << np.uint64(p & 63)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us = np.unique(d["sess"]); sidx = np.searchsorted(us, d["sess"]).astype(np.int64)
    cut = np.int64(int(0.65 * len(us)))
    nv = len(EXITS)
    EB = np.zeros((nv, nbars), np.int64); EP = np.zeros((nv, nbars), np.float64)
    OK = np.zeros((nv, nbars), np.int64)
    for vi, (am, tp, fl) in enumerate(EXITS):
        price_one(o, h, l, c, atr_, mod, side, am, tp, fl, EB[vi], EP[vi], OK[vi])
    tot = len(combos) * nv
    z = lambda t: np.zeros(tot, t)
    rn, rw, ln, lw = z(np.int32), z(np.int32), z(np.int32), z(np.int32)
    rs, ls = z(np.float32), z(np.float32)
    sweep_wins(B, combos, nbars, EB, EP, OK, sidx, cut, rn, rs, rw, ln, ls, lw)
    if verbose:
        print(f"  {tf}m {'long ' if side == 1 else 'short'}: {len(combos):,} rules x {nv} "
              f"= {tot:,} combinations", flush=True)
    return dict(tf=tf, side=side, d=d, names=names, combos=combos, split=(ns, npb, nrs), nv=nv,
                win=win, rn=rn.astype(float), rw=rw.astype(float), ln=ln.astype(float),
                lw=lw.astype(float), rs=rs.astype(float), ls=ls.astype(float))


def gate(S, verbose=True):
    nv = S["nv"]; combos = S["combos"]; ns, npb, nrs = S["split"]
    base = window_baseline(S["d"], S["side"], S["win"])
    wr = np.where(S["rn"] > 0, 100 * S["rw"] / np.maximum(S["rn"], 1), np.nan)
    dpt = np.where(S["rn"] > 0, S["rs"] / np.maximum(S["rn"], 1), np.nan)
    v = np.arange(len(S["rn"])) % nv
    rule_i = np.arange(len(S["rn"])) // nv
    bw = np.array([base[i][0] for i in range(nv)])
    bd = np.array([base[i][1] for i in range(nv)])
    beats = (wr > bw[v]) & (dpt > bd[v])
    ntri = np.array([(combos[r] >= 0).sum() for r in range(len(combos))])
    ok = (S["rn"] >= MIN_RES) & (S["ln"] >= MIN_LOK) & beats & (ntri[rule_i] == 3)
    rmap = {tuple(sorted(int(x) for x in combos[r] if x >= 0)): r for r in range(len(combos))}
    keep = []
    for k in np.flatnonzero(ok):
        r, vv = int(rule_i[k]), int(v[k])
        idxs = tuple(sorted(int(x) for x in combos[r] if x >= 0))
        good = True
        for nsub in (1, 2):
            for sub in combinations(idxs, nsub):
                j = rmap.get(sub)
                if j is None:
                    continue
                q = j * nv + vv
                if S["rn"][q] < 20:
                    continue
                if not (wr[q] > bw[vv] and dpt[q] > bd[vv]):
                    good = False; break
            if not good:
                break
        if good:
            keep.append(k)
    if verbose:
        print(f"     window baseline at each geometry: {np.nanmin(bw):.1f}-{np.nanmax(bw):.1f}% "
              f"win, ${np.nanmin(bd):.1f} to ${np.nanmax(bd):.1f}/trade")
        print(f"     {int(((S['rn'] >= MIN_RES) & (ntri[rule_i] == 3)).sum()):,} triples with "
              f"{MIN_RES}+ research trades -> {int(ok.sum()):,} beat the window baseline "
              f"-> {len(keep):,} survive subset coherence", flush=True)
    out = []
    for k in keep:
        r, vv = int(rule_i[k]), int(v[k])
        am, tp, fl = EXITS[vv]
        out.append(dict(tf=S["tf"], side=S["side"],
                        rule=[S["names"][i] for i in combos[r] if i >= 0],
                        am=float(am), flat=int(fl), wr=float(wr[k]), base_wr=float(bw[vv]),
                        dpt=float(dpt[k]), base_dpt=float(bd[vv]),
                        n_res=int(S["rn"][k]), n_lok=int(S["ln"][k]),
                        res=float(S["rs"][k]), lok=float(S["ls"][k]),
                        wr_lok=100 * float(S["lw"][k] / max(S["ln"][k], 1)),
                        edge=float(wr[k] - bw[vv])))
    return out


def rule_trig(tf, side, rule):
    d, names, M, (ns, npb, nrs), win = pool(tf, side)
    M[ns + npb:] &= win
    ix = {n: i for i, n in enumerate(names)}
    m = np.ones(len(d["c"]), bool)
    for q in rule:
        m &= M[ix[q]]
    return d, np.flatnonzero(m).astype(np.int64)


if __name__ == "__main__":
    tfs = [int(x) for x in sys.argv[1:]] or [5, 15, 30]
    print(f"TREND -> PULLBACK -> RESUMPTION, {WINDOW[0]//60:02d}:00-{WINDOW[1]//60:02d}:00 "
          f"New York, scored against the WINDOW BASELINE\n")
    allo = []
    for tf in tfs:
        for side in (1, -1):
            allo += gate(sweep_side(tf, side))
    allo.sort(key=lambda x: -x["edge"])
    np.save("results/trendpool/trendpool_gated.npy", np.array(allo, dtype=object), allow_pickle=True)
    print(f"\n{len(allo):,} rule/geometry pairs beat the window baseline and hold subset coherence")
    print(f"\n  {'rule':<74}{'tf':>4}{'dir':>6}{'n':>5}{'win%':>7}{'base':>7}{'edge':>7}{'res $':>8}")
    for x in allo[:12]:
        print(f"  {' + '.join(x['rule'])[:72]:<74}{x['tf']:>4}"
              f"{'long' if x['side'] == 1 else 'short':>6}{x['n_res']:>5}{x['wr']:>7.1f}"
              f"{x['base_wr']:>7.1f}{x['edge']:>+7.1f}{x['res']:>8,.0f}")
