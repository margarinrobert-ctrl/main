"""V51 -- the full sweep. 1,161,216 configurations, and the deliverable is the SHAPE of the
population, not a row. The brief is explicit about this and so is the branch's history: a
1,290,240-cell grid came back 58% profitable and 0.3% of its top 1000 stayed profitable out of
sample, and a 110,250-config sweep bought +0.098 R against the un-swept starting point's +0.097.

SEARCH MARKET: US100L, first 70% of bars. LOCKED: the last 30%, read once at the end.
HELD BACK ENTIRELY: US30L. Its 15m returns correlate 0.758 with US100's over an overlapping
calendar, so it is the best available second test and NOT an independent one -- say so with the
number, per `STUDY_TREND_LONG`.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v51")
import v51feat as V         # noqa: E402
import v51tensor as T       # noqa: E402

SPLIT = 0.70
TFS = (15, 30, 60)
MARKETS = ("US100L", "US30L")


def sweep_market(market, tf, cost_mult=1.0):
    P = V.build(market, tf)
    ck = V.COSTS[market]
    cost, slip = ck["cost"] * cost_mult, ck["slip"] * cost_mult
    cut = int(P["n"] * SPLIT)

    uni = np.flatnonzero(V.entry_mask(P, min(V.ENT_N)))      # the 10-bar set contains all others
    pos_of_bar = -np.ones(P["n"], np.int64)
    pos_of_bar[uni] = np.arange(len(uni))

    # ---- the exit tensor: one walk per (exitN, stopN, flatten) -------------------------------
    tensor = {}
    for xn in V.EXIT_N:
        elo = P["exit_lo"][xn]
        for sn in V.STOP_N:
            for fc in V.FLAT_CFG:
                fm = -1 if fc == 0 else V.WINDOWS[fc][1]
                tensor[(xn, sn, fc)] = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"],
                                              uni, elo, float(sn), fm, P["mod"],
                                              cost, slip, V.MAX_HOLD)

    # sessions grouped by the flatten they imply, so each geometry scores only its own
    ss_by_flat = {fc: np.array([i for i, (w, f) in enumerate(V.SESS)
                                if (f == 1 and w == fc) or (f == 0 and fc == 0)], np.int64)
                  for fc in V.FLAT_CFG}

    rows = []
    for en in V.ENT_N:
        bars = np.flatnonzero(V.entry_mask(P, en))
        sub = pos_of_bar[bars]
        MA, CX, AB, SS = V.filter_masks(P, bars)
        for xn in V.EXIT_N:
            for sn in V.STOP_N:
                for fc in V.FLAT_CFG:
                    ss_ids = ss_by_flat[fc]
                    if len(ss_ids) == 0:
                        continue
                    xb, R = tensor[(xn, sn, fc)]
                    tot = MA.shape[0] * CX.shape[0] * AB.shape[0] * len(ss_ids)
                    on = np.zeros(tot, np.int64); os_ = np.zeros(tot)
                    ow = np.zeros(tot, np.int64); ogp = np.zeros(tot); ogl = np.zeros(tot)
                    onl = np.zeros(tot, np.int64); osl = np.zeros(tot)
                    T.score_all(sub, bars, xb, R, MA, CX, AB, SS, ss_ids, cut,
                                on, os_, ow, ogp, ogl, onl, osl)
                    nma, ncx, nab, nss = MA.shape[0], CX.shape[0], AB.shape[0], len(ss_ids)
                    t = np.arange(tot)
                    ia = t // (ncx * nab * nss)
                    r = t - ia * (ncx * nab * nss)
                    ic = r // (nab * nss)
                    r2 = r - ic * (nab * nss)
                    ib = r2 // nss
                    isx = ss_ids[r2 - ib * nss]
                    rows.append(pd.DataFrame(dict(
                        market=market, tf=tf, entN=en, exitN=xn, stopN=sn,
                        ma=ia.astype(np.int8), cx=ic.astype(np.int8), ab=ib.astype(np.int8),
                        ss=isx.astype(np.int8),
                        n=on, sumR=os_, win=ow, gp=ogp, gl=ogl, nlk=onl, sumRlk=osl)))
    D = pd.concat(rows, ignore_index=True)
    D["R"] = np.where(D.n > 0, D.sumR / np.maximum(D.n, 1), np.nan)
    D["Rlk"] = np.where(D.nlk > 0, D.sumRlk / np.maximum(D.nlk, 1), np.nan)
    D["pf"] = np.where(D.gl > 0, D.gp / np.maximum(D.gl, 1e-9), np.nan)
    D["winpct"] = np.where(D.n > 0, 100.0 * D.win / np.maximum(D.n, 1), np.nan)
    return D


def main(cost_mult=1.0, tag="base"):
    out = []
    for m in MARKETS:
        for tf in TFS:
            t0 = time.time()
            D = sweep_market(m, tf, cost_mult)
            print(f"  {m} {tf}m: {len(D):,} configurations in {time.time()-t0:6.1f}s")
            out.append(D)
    A = pd.concat(out, ignore_index=True)
    A.to_parquet(f"results/v51/v51_grid_{tag}.parquet", index=False)
    print(f"\n  {len(A):,} configurations total -> results/v51/v51_grid_{tag}.parquet")
    return A


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 1.0,
         sys.argv[2] if len(sys.argv) > 2 else "base")
