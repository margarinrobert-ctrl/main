"""The five phases, on the daily-trend pullback family.

Same gates as everything else on this branch, with one structural change that is the whole point:

  DIRECTION IS NOT SEARCHED. The daily trend state fixes the side, so the long rules are only ever
  compared against the LONG base rate and the short rules against the SHORT one, and no rule can
  win by discovering that this sample went up. That removes the free parameter RESEARCH_PROTOCOL.md
  4c calls the most dangerous one here.

Enumeration includes singletons and pairs as well as the full state x pullback x resumption
triples, not as candidates but so SUBSET COHERENCE can be checked: a three-legged rule whose legs
are worthless alone is an interaction found by search.

Usage: python3 research/pullback_search.py [tf ...]
"""
from __future__ import annotations

import sys
from itertools import combinations, product

import numpy as np

sys.path.insert(0, "research")
from alpha_factory2 import price_one
from oner_hunt import sweep_wins
from pullback import EXITS, WINDOW, pool

MIN_RES, MIN_LOK = 30, 12


def enumerate_rules(ns, npb, nrs):
    """singletons, all pairs, then every state x pullback x resumption triple."""
    a = list(range(ns))
    b = list(range(ns, ns + npb))
    c = list(range(ns + npb, ns + npb + nrs))
    rules = [(i, -1, -1) for i in a + b + c]
    rules += [(i, j, -1) for i, j in combinations(a + b + c, 2)]
    rules += [(i, j, k) for i, j, k in product(a, b, c)]
    return np.array(rules, np.int32)


def sweep_side(tf, side, verbose=True):
    d, names, M, (ns, npb, nrs), win = pool(tf, side)
    # the RESUMPTION is the bar the order is sent on, so the window is ANDed into those rows.
    # Doing it here rather than as a rule condition keeps all three slots for the structure.
    M[ns + npb:] &= win
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
              f"geometries = {tot:,}", flush=True)
    return dict(tf=tf, side=side, d=d, names=names, combos=combos, split=(ns, npb, nrs), nv=nv,
                rn=rn.astype(float), rw=rw.astype(float), ln=ln.astype(float),
                lw=lw.astype(float), rs=rs.astype(float), ls=ls.astype(float))


def base_rates(S):
    """Population mean research win rate per geometry, for THIS side."""
    nv = S["nv"]
    v = np.arange(len(S["rn"])) % nv
    live = S["rn"] >= MIN_RES
    wr = np.where(S["rn"] > 0, 100 * S["rw"] / np.maximum(S["rn"], 1), np.nan)
    out = np.full(nv, np.nan)
    for i in range(nv):
        m = live & (v == i)
        if m.sum() > 40:
            out[i] = np.nanmean(wr[m])
    return out


def gate(S, verbose=True):
    nv = S["nv"]; combos = S["combos"]; ns, npb, nrs = S["split"]
    base = base_rates(S)
    wr = np.where(S["rn"] > 0, 100 * S["rw"] / np.maximum(S["rn"], 1), np.nan)
    v = np.arange(len(S["rn"])) % nv
    rule_i = np.arange(len(S["rn"])) // nv
    exc = wr - base[v]
    is_triple = np.array([(combos[r] >= 0).sum() == 3 for r in range(len(combos))])
    ok = (S["rn"] >= MIN_RES) & (S["ln"] >= MIN_LOK) & (S["rs"] > 0) & (exc > 0) & is_triple[rule_i]
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
                if wr[q] - base[vv] <= 0:
                    good = False; break
            if not good:
                break
        if good:
            keep.append(k)
    if verbose:
        print(f"     {int(((S['rn'] >= MIN_RES) & is_triple[rule_i]).sum()):,} triples with "
              f"{MIN_RES}+ research trades -> {int(ok.sum()):,} beat their base and make money "
              f"-> {len(keep):,} survive subset coherence")
    out = []
    for k in keep:
        r, vv = int(rule_i[k]), int(v[k])
        am, tp, fl = EXITS[vv]
        out.append(dict(tf=S["tf"], side=S["side"],
                        rule=[S["names"][i] for i in combos[r] if i >= 0],
                        am=float(am), flat=int(fl), exc=float(exc[k]), wr=float(wr[k]),
                        base=float(base[vv]), n_res=int(S["rn"][k]), n_lok=int(S["ln"][k]),
                        res=float(S["rs"][k]), lok=float(S["ls"][k]),
                        wr_lok=100 * float(S["lw"][k] / max(S["ln"][k], 1))))
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
    print(f"DAILY TREND -> PULLBACK -> RESUMPTION, entries {WINDOW[0]//60:02d}:00-"
          f"{WINDOW[1]//60:02d}:00 New York\n")
    allo = []
    for tf in tfs:
        for side in (1, -1):
            S = sweep_side(tf, side)
            allo += gate(S)
    allo.sort(key=lambda x: -x["exc"])
    np.save("results/pullback/pullback_gated.npy", np.array(allo, dtype=object), allow_pickle=True)
    print(f"\n{len(allo):,} rule/geometry pairs survive every research-block gate")
    print(f"\n  {'rule':<64}{'tf':>4}{'dir':>6}{'stop':>5}{'flat':>6}{'n':>5}{'win%':>7}"
          f"{'base':>6}{'exc':>7}{'res $':>8}")
    for x in allo[:15]:
        print(f"  {' + '.join(x['rule'])[:62]:<64}{x['tf']:>4}"
              f"{'long' if x['side'] == 1 else 'short':>6}{x['am']:>5.1f}"
              f"{(x['flat'] // 60 if x['flat'] else 0):>6}{x['n_res']:>5}{x['wr']:>7.1f}"
              f"{x['base']:>6.1f}{x['exc']:>+7.1f}{x['res']:>8,.0f}")
