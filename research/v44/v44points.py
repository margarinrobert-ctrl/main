"""V44 -- the same trades expressed in NQ POINTS and in dollars, beside the ATR-normalised figures.

WHY BOTH ARE REPORTED, NOT JUST POINTS. ATR units are what makes two timeframes and two blocks
comparable; points are what is actually risked and earned. They disagree here for a reason that is
recorded on this branch: OUR NQ PRICE LEVELS ARE SYNTHETIC. The stored series reads 13,915.8 on
2023-01-10 where the real Nasdaq-100 was near 11,100, and the ratio decays smoothly from 1.253 to
1.036 across the sample. Returns and ATR-normalised quantities are unaffected; POINT and DOLLAR
magnitudes are INFLATED EARLY, which is the research block. So a points figure from research is not
directly comparable to one from locked, and the ATR column is the one to trust for that comparison.

Dollars are MNQ at $2.00 a point (`data.COSTS["NQ"]["point_value"]`). Costs are the branch's real
MNQ stack: 0.72 points of fee plus 0.25 of slippage per side.

MFE and MAE here are walked on the 1-MINUTE path between the fill and the actual exit, so they are
the excursions the position really experienced, not a bar-level approximation of them.

Usage: python research/v44/v44points.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v44")
import data as TD           # noqa: E402
import v44build as B        # noqa: E402
import v44final as V        # noqa: E402


@njit(cache=True)
def walk_pts(o1, h1, l1, c1, mod1, e_idx, stop_px, tp_px, flat_min, cost, slip):
    """As B.walk, but also returns MFE and MAE in POINTS off the fill, on the 1-minute path."""
    n = len(e_idx); m = len(c1)
    pnl = np.zeros(n); why = np.zeros(n, np.int64); mins = np.zeros(n, np.int64)
    xi = np.zeros(n, np.int64); mfe = np.zeros(n); mae = np.zeros(n)
    for k in range(n):
        a = e_idx[k]; px = o1[a] + slip
        s = stop_px[k]; t = tp_px[k]
        j = a; r = 0; out = 0.0
        best = -1e18; worst = 1e18
        while j < m:
            if h1[j] - px > best:
                best = h1[j] - px
            if px - l1[j] > -worst:
                worst = -(px - l1[j])
            if l1[j] <= s:
                r = 1; out = s - slip
                break
            if h1[j] >= t:
                r = 2; out = t - slip
                break
            if mod1[j] >= flat_min:
                r = 3; out = c1[j] - slip
                break
            j += 1
        if r == 0:
            j = m - 1; out = c1[j] - slip
        pnl[k] = out - px - cost
        why[k] = r; mins[k] = j - a; xi[k] = j
        mfe[k] = best; mae[k] = -worst
    return pnl, why, mins, xi, mfe, mae


def run(tf, win, k, sN, tpR):
    P, picks, d1, m1 = V.context(tf, win)
    o1, h1, l1, c1 = d1["o"], d1["h"], d1["l"], d1["c"]
    mod1 = np.asarray(d1["mod"], int)
    cost = TD.COSTS["NQ"]["cost_pts"]; slip = TD.COSTS["NQ"]["slip_pts"]
    atr, n = P["atr"], P["n"]
    conds = np.vstack([B.condition(P, r) for r in picks])
    sig = P["elig"] & (conds.sum(axis=0) >= k) & np.isfinite(atr) & (atr > 0)
    sig[n - 2:] = False
    idx = np.flatnonzero(sig)
    ent = m1[idx + 1]; keep = np.isfinite(ent)
    idx, ent = idx[keep], ent[keep].astype(np.int64)
    px0 = o1[ent]; risk = sN * atr[idx]
    pnl, why, mins, xi, mfe, mae = walk_pts(o1, h1, l1, c1, mod1, ent, px0 - risk,
                                            px0 + tpR * risk, B.FLAT_MIN, cost, slip)
    keep2 = np.ones(len(ent), bool); last = -1
    for z in range(len(ent)):
        if ent[z] <= last:
            keep2[z] = False
        else:
            last = xi[z]
    sl = keep2
    return dict(P=P, idx=idx[sl], pnl=pnl[sl], why=why[sl], mins=mins[sl],
                risk=risk[sl], atr=atr[idx][sl], mfe=mfe[sl], mae=mae[sl])


def main():
    pv = TD.COSTS["NQ"]["point_value"]
    rows = []
    for tf, cfg in V.FROZEN.items():
        for wname, win in (("07:00-11:00", B.WIN), ("09:30-11:00", (570, 660))):
            T = run(tf, win, cfg["k"], cfg["stop"], cfg["tp"])
            res = T["P"]["res"]
            print("\n" + "=" * 100)
            print(f"  NQ {tf}m  {wname} NY  {cfg['k']}/4 conditions  stop {cfg['stop']} ATR  "
                  f"target {cfg['tp']} R   MNQ ${pv:.2f}/pt")
            print("=" * 100)
            for bname, blk in (("research", res), ("locked", ~res)):
                s = blk[T["idx"]]
                if s.sum() < 20:
                    print(f"    {bname}: {int(s.sum())} trades -- too few"); continue
                atr, risk = T["atr"][s], T["risk"][s]
                mfe, mae, pnl, why, mins = (T[x][s] for x in ("mfe", "mae", "pnl", "why", "mins"))
                print(f"    {bname:<9} n {int(s.sum()):>4}   ATR at signal: median {np.median(atr):.2f} pts"
                      f"   stop distance: median {np.median(risk):.2f} pts (${np.median(risk)*pv:,.0f})"
                      f"   target: {np.median(risk)*cfg['tp']:.2f} pts")
                print(f"              MFE  median {np.median(mfe):>7.2f} pts  mean {mfe.mean():>7.2f}"
                      f"   (${np.median(mfe)*pv:>7,.0f} / ${mfe.mean()*pv:>7,.0f})"
                      f"   in ATR: {np.median(mfe/atr):.2f} / {(mfe/atr).mean():.2f}")
                print(f"              MAE  median {np.median(mae):>7.2f} pts  mean {mae.mean():>7.2f}"
                      f"   (${np.median(mae)*pv:>7,.0f} / ${mae.mean()*pv:>7,.0f})"
                      f"   in ATR: {np.median(mae/atr):.2f} / {(mae/atr).mean():.2f}")
                for code, nm in ((2, "WINNERS (target)"), (1, "LOSERS (stop)")):
                    m = why == code
                    if m.sum() < 5:
                        continue
                    print(f"              {nm:<17} n {int(m.sum()):>4}  "
                          f"MFE {np.median(mfe[m]):>6.2f} pts  MAE {np.median(mae[m]):>6.2f} pts  "
                          f"median time {np.median(mins[m]):>4.0f} min")
                print(f"              net per trade {pnl.mean():+.2f} pts  (${pnl.mean()*pv:+,.2f})"
                      f"   total {pnl.sum():+,.0f} pts  (${pnl.sum()*pv:+,.0f})")
                rows.append(dict(tf=tf, win=wname, block=bname, n=int(s.sum()),
                                 atr_med=float(np.median(atr)), stop_pts=float(np.median(risk)),
                                 mfe_pts_med=float(np.median(mfe)), mfe_pts_mean=float(mfe.mean()),
                                 mae_pts_med=float(np.median(mae)), mae_pts_mean=float(mae.mean()),
                                 mfe_atr=float((mfe / atr).mean()), mae_atr=float((mae / atr).mean()),
                                 pts=float(pnl.mean()), usd=float(pnl.mean() * pv)))
    d = pd.DataFrame(rows)
    d.to_csv("results/v44/v44_points.csv", index=False)
    return d


if __name__ == "__main__":
    main()
