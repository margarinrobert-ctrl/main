"""V45 -- engineering the take profit from MFE/MAE: the theory, its bounds, and the practice.

THEORY FIRST, AND ITS LIMIT STATED HONESTLY. For a long with stop S and target T (points) and a
round turn of C points, expectancy is zero at

    p* = (S + C) / (T + S)                       [BREAK-EVEN WIN RATE]

and the profit factor at win rate p is  PF = p(T - C) / [(1 - p)(S + C)].

The tempting move is to read p off the MFE distribution: P(MFE >= T) is the share of trades whose
favourable excursion ever reached the target. THAT NUMBER IS AN UPPER BOUND, NOT A WIN RATE.
MFE and MAE say whether each barrier was reached, never WHICH CAME FIRST. So the distributions
alone deliver a bracket:

    p_lower = P(MFE >= T  AND  MAE <  S)         both settled: the target was reached, the stop
                                                 was never reached -- a win under any ordering
    p_upper = P(MFE >= T)                        every trade that ever touched the target
    ambiguous = p_upper - p_lower                both barriers reached; only the PATH decides

The width of that bracket is the whole reason a bar-level study of a tight barrier pair is a
statement about a tie-break rule rather than about the market. This module reports the bracket,
then resolves it on the TRUE 1-MINUTE PATH, and prints where the realised win rate falls inside it.

SELECTION IS ON RESEARCH. The geometry is chosen on the first 65% of sessions by marginal average
per axis -- never by the top cell of the grid, which is the max of its own draws -- and the locked
block is read once, at the end, with a matched control.

EXCURSIONS RUN TO THE 11:00 FLATTEN WITH NO BARRIERS. That is the correct unconstrained horizon
for this scalp: it is exactly how far the trade could have gone, so P(MFE >= T) is exactly the
probability the target was reachable before the bell.

Usage: python research/v45/v45tp.py
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
import v44feat as F         # noqa: E402

WIN = (420, 660)            # 07:00-11:00 New York, as briefed
FLAT_MIN = 660              # hard flatten at 11:00
SPLIT = 0.65
STOPS = (0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0)      # ATR
TPS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0)         # R


@njit(cache=True)
def free_run(o1, h1, l1, c1, mod1, e_idx, flat_min):
    """MFE, MAE and the flatten price, in POINTS off the fill, with NO barriers.

    This is the unconstrained excursion: how far the trade could have gone either way before the
    bell. Everything the theory needs comes from these three numbers."""
    n = len(e_idx); m = len(c1)
    mfe = np.zeros(n); mae = np.zeros(n); endpx = np.zeros(n); mins = np.zeros(n, np.int64)
    for k in range(n):
        a = e_idx[k]; px = o1[a]
        best = 0.0; worst = 0.0
        j = a
        while j < m:
            if h1[j] - px > best:
                best = h1[j] - px
            if px - l1[j] > worst:
                worst = px - l1[j]
            if mod1[j] >= flat_min:
                break
            j += 1
        if j >= m:
            j = m - 1
        mfe[k] = best; mae[k] = worst; endpx[k] = c1[j]; mins[k] = j - a
    return mfe, mae, endpx, mins


@njit(cache=True)
def barrier_run(o1, h1, l1, c1, mod1, e_idx, stop_px, tp_px, flat_min, cost, slip, lock):
    """First-touch on the 1-minute path. `lock` enforces one live position at a time."""
    n = len(e_idx); m = len(c1)
    pnl = np.zeros(n); why = np.zeros(n, np.int64); mins = np.zeros(n, np.int64)
    take = np.zeros(n, np.bool_)
    last_exit = -1
    for k in range(n):
        a = e_idx[k]
        if lock and a <= last_exit:
            continue
        px = o1[a] + slip
        s = stop_px[k]; t = tp_px[k]
        j = a; r = 0; out = 0.0
        while j < m:
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
        why[k] = r; mins[k] = j - a; take[k] = True
        last_exit = j
    return pnl, why, mins, take


def prep(tf):
    d = TD.bars("NQ", tf)
    d1 = TD.bars("NQ", 1)
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    feats, atr = F.build(o, h, l, c, v)
    mod = np.asarray(d["mod"], int)
    n = len(c)
    elig = (mod >= WIN[0]) & (mod < WIN[1]) & np.isfinite(atr) & (atr > 0)
    elig[n - 2:] = False
    t = pd.to_datetime(pd.Series(d["idx"])); t1 = pd.to_datetime(pd.Series(d1["idx"]))
    m1 = pd.Series(np.arange(len(t1)), index=t1.values).reindex(t.values).to_numpy()
    idx = np.flatnonzero(elig)
    ent = m1[idx + 1]
    keep = np.isfinite(ent)
    idx, ent = idx[keep], ent[keep].astype(np.int64)
    return dict(d=d, d1=d1, atr=atr, feats=feats, idx=idx, ent=ent, n=n,
                res=np.arange(n) < int(n * SPLIT), tf=tf)


def theory(P, blk, S_atr, T_r, mfe, mae, cost):
    """The bracket, from the excursion distributions alone. No ordering is assumed."""
    s = blk[P["idx"]]
    atr = P["atr"][P["idx"]][s]
    Sp = S_atr * atr
    Tp = T_r * Sp
    f, a = mfe[s], mae[s]
    hit_t = f >= Tp
    hit_s = a >= Sp
    p_lower = float(np.mean(hit_t & ~hit_s))
    p_upper = float(np.mean(hit_t))
    p_star = float(np.mean((Sp + cost) / (Tp + Sp)))
    return dict(p_lower=p_lower, p_upper=p_upper, ambiguous=p_upper - p_lower,
                p_star=p_star, n=int(s.sum()),
                reach_t=float(np.mean(hit_t)), reach_s=float(np.mean(hit_s)))


def pf_at(p, S, T, C):
    """Profit factor implied by a win rate, exactly. Losers pay S+C, winners take T-C."""
    if p <= 0 or p >= 1 or (T - C) <= 0:
        return np.nan
    return (p * (T - C)) / ((1 - p) * (S + C))


def run(tf):
    P = prep(tf)
    d1 = P["d1"]
    o1, h1, l1, c1 = d1["o"], d1["h"], d1["l"], d1["c"]
    mod1 = np.asarray(d1["mod"], int)
    cost_pts = TD.COSTS["NQ"]["cost_pts"]; slip = TD.COSTS["NQ"]["slip_pts"]
    C = cost_pts + 2 * slip                      # the full round turn a trade actually pays
    mfe, mae, endpx, fmins = free_run(o1, h1, l1, c1, mod1, P["ent"], FLAT_MIN)
    atr_all = P["atr"][P["idx"]]
    rows = []
    for S in STOPS:
        for T in TPS:
            Sp = S * atr_all
            Tp = T * Sp
            pnl, why, mins, take = barrier_run(o1, h1, l1, c1, mod1, P["ent"],
                                               o1[P["ent"]] - Sp, o1[P["ent"]] + Tp,
                                               FLAT_MIN, cost_pts, slip, True)
            for bname, blk in (("research", P["res"]), ("locked", ~P["res"])):
                th = theory(P, blk, S, T, mfe, mae, C)
                sel = blk[P["idx"]] & take
                if sel.sum() < 30:
                    continue
                p_, w_ = pnl[sel], why[sel]
                gp = p_[p_ > 0].sum(); gl = -p_[p_ < 0].sum()
                win = float((p_ > 0).mean())
                rows.append(dict(
                    tf=tf, stop_atr=S, tp_r=T, block=bname, n=int(sel.sum()),
                    n_signals=int((blk[P["idx"]]).sum()),
                    p_lower=th["p_lower"], p_upper=th["p_upper"], ambiguous=th["ambiguous"],
                    p_star=th["p_star"], reach_t=th["reach_t"], reach_s=th["reach_s"],
                    win=win, pf=float(gp / gl) if gl > 0 else np.nan,
                    pts=float(p_.mean()),
                    pf_theory_up=pf_at(th["p_upper"], S * np.median(atr_all),
                                       T * S * np.median(atr_all), C),
                    pf_theory_lo=pf_at(th["p_lower"], S * np.median(atr_all),
                                       T * S * np.median(atr_all), C),
                    hit_tp=float((w_ == 2).mean()), hit_sl=float((w_ == 1).mean()),
                    flat=float((w_ == 3).mean()),
                    t_tp=float(np.median(mins[sel][w_ == 2])) if (w_ == 2).any() else np.nan,
                    t_sl=float(np.median(mins[sel][w_ == 1])) if (w_ == 1).any() else np.nan))
    return pd.DataFrame(rows), mfe, mae, atr_all, P


def main():
    out = []
    for tf in (5, 15):
        df, mfe, mae, atr, P = run(tf)
        out.append(df)
        res = P["res"][P["idx"]]
        print("\n" + "=" * 112)
        print(f"  NQ {tf}m   07:00-11:00 NY   long   flatten 11:00   1-minute path   "
              f"round turn {TD.COSTS['NQ']['cost_pts'] + 2*TD.COSTS['NQ']['slip_pts']:.2f} pts")
        print("=" * 112)
        print(f"  Unconstrained excursion to the bell, RESEARCH, {int(res.sum()):,} bars:")
        print(f"     MFE mean {np.mean(mfe[res]):.2f} pts  median {np.median(mfe[res]):.2f}"
              f"   |   MAE mean {np.mean(mae[res]):.2f}  median {np.median(mae[res]):.2f}"
              f"   |   ATR median {np.median(atr[res]):.2f}")
    d = pd.concat(out, ignore_index=True)
    d.to_csv("results/v45/v45_tp_grid.csv", index=False)
    return d


if __name__ == "__main__":
    main()
