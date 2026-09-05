"""V52 -- the pasted Turtle script with one entry, one exit, the four requested filters, and its own
two gates swept in BOTH directions. 4,644,864 configurations.

Searched on US100L's first 70% ONLY. US100L's last 30% and the whole of US30L are held back.
"""
from __future__ import annotations
import sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v51"); sys.path.insert(0, "research/v52")
import v51tensor as T51     # noqa: E402
import v52feat as V         # noqa: E402
import v52tensor as T       # noqa: E402

SPLIT = 0.70
TFS = (60, 120, 240)
MARKETS = ("US100L", "US30L")


def sweep(market, tf, cost_mult=1.0):
    P = V.build(market, tf)
    ck = V.COSTS[market]
    cost, slip = ck["cost"] * cost_mult, ck["slip"] * cost_mult
    cut = int(P["n"] * SPLIT)
    uni = np.flatnonzero(V.entry_mask(P, min(V.ENT_N)))
    pos = -np.ones(P["n"], np.int64); pos[uni] = np.arange(len(uni))
    tensor = {}
    for xn in V.EXIT_N:
        for sn in V.STOP_N:
            for fc in V.FLAT_CFG:
                fm = -1 if fc == 0 else V.WINDOWS[fc][1]
                tensor[(xn, sn, fc)] = T51.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], uni,
                                                P["exit_lo"][xn], float(sn), fm, P["mod"],
                                                cost, slip, V.MAX_HOLD)
    ss_by_flat = {fc: np.array([i for i, (w, f) in enumerate(V.SESS)
                                if (f == 1 and w == fc) or (f == 0 and fc == 0)], np.int64)
                  for fc in V.FLAT_CFG}
    rows = []
    for en in V.ENT_N:
        bars = np.flatnonzero(V.entry_mask(P, en))
        sub = pos[bars]
        MA, CX, AB, SS, AD, EX = V.filter_masks(P, bars)
        for xn in V.EXIT_N:
            for sn in V.STOP_N:
                for fc in V.FLAT_CFG:
                    ss_ids = ss_by_flat[fc]
                    xb, R = tensor[(xn, sn, fc)]
                    nma, ncx, nab = MA.shape[0], CX.shape[0], AB.shape[0]
                    nad, nex, nss = AD.shape[0], EX.shape[0], len(ss_ids)
                    tot = nma * ncx * nab * nad * nex * nss
                    on = np.zeros(tot, np.int64); os_ = np.zeros(tot); ow = np.zeros(tot, np.int64)
                    ogp = np.zeros(tot); ogl = np.zeros(tot)
                    onl = np.zeros(tot, np.int64); osl = np.zeros(tot)
                    T.score_all(sub, bars, xb, R, MA, CX, AB, SS, AD, EX, ss_ids, cut,
                                on, os_, ow, ogp, ogl, onl, osl)
                    t = np.arange(tot)
                    d5 = nss; d4 = nex * d5; d3 = nad * d4; d2 = nab * d3; d1 = ncx * d2
                    ia = t // d1
                    ic = (t // d2) % ncx
                    ib = (t // d3) % nab
                    idd = (t // d4) % nad
                    ie = (t // d5) % nex
                    isx = ss_ids[t % nss]
                    rows.append(pd.DataFrame(dict(
                        market=market, tf=tf, entN=en, exitN=xn, stopN=sn,
                        ma=ia.astype(np.int8), cx=ic.astype(np.int8), ab=ib.astype(np.int8),
                        adx=idd.astype(np.int8), ext=ie.astype(np.int8), ss=isx.astype(np.int8),
                        n=on, sumR=os_, win=ow, gp=ogp, gl=ogl, nlk=onl, sumRlk=osl)))
    D = pd.concat(rows, ignore_index=True)
    D["R"] = np.where(D.n > 0, D.sumR / np.maximum(D.n, 1), np.nan)
    D["Rlk"] = np.where(D.nlk > 0, D.sumRlk / np.maximum(D.nlk, 1), np.nan)
    D["pf"] = np.where(D.gl > 0, D.gp / np.maximum(D.gl, 1e-9), np.nan)
    return D


if __name__ == "__main__":
    out = []
    for m in MARKETS:
        for tf in TFS:
            t0 = time.time()
            D = sweep(m, tf)
            print(f"  {m} {tf}m: {len(D):,} configurations in {time.time()-t0:6.1f}s")
            out.append(D)
    A = pd.concat(out, ignore_index=True)
    A.to_parquet("results/v52/v52_grid.parquet", index=False)
    print(f"\n  {len(A):,} configurations -> results/v52/v52_grid.parquet")
