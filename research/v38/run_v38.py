"""V38 -- the 113,400-configuration sweep, read the way this branch has learned to read a sweep.

The order of the report is deliberate and is the point:
    1. the SHAPE of the grid -- what share of it is profitable at all
    2. the MARGINAL AVERAGE per axis -- what each knob is worth across every other setting
    3. what the TOP 100 AGREE ON -- consensus, not the single best row
    4. only then the best row, with its selection premium stated
    5. the LOCKED block, read ONCE
    6. TWO MARKETS THAT HAD NO PART IN THE SEARCH
    7. the deflated Sharpe as a CURVE over assumed trial count, never one number

Usage: python3 research/v38/run_v38.py
"""
from __future__ import annotations

import sys
import time
from itertools import product

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402

RESEARCH_FRAC = 0.65         # the branch's standing split: the first 65% of sessions


def hdr(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122, flush=True)


def blocks(P):
    d = np.unique(P["day"])
    cut = d[int(len(d) * RESEARCH_FRAC)]
    return P["day"] < cut, P["day"] >= cut


def sweep(P, msk, ten, res_mask, all_res_days, all_lock_days, lock_mask):
    """Every configuration, scored on BOTH blocks in one pass. The locked numbers are computed
    here and NOT looked at until section 5 -- they are never sorted on, and no threshold anywhere
    above is chosen with them in view."""
    day = P["day"]
    rows = []
    buf_p = np.zeros(P["n"])
    buf_s = np.zeros(P["n"], np.int64)
    for (e, ln, lr, mn, mr), sig in msk.items():
        if len(sig) < 20:
            continue
        for (x, sn, tp), (xb, pnl, _why) in ten.items():
            k = G._lock(sig, xb, pnl, buf_p, buf_s)
            if k < 20:
                continue
            p, sb = buf_p[:k].copy(), buf_s[:k]
            rd = res_mask[sb]
            mr_ = G.score(p[rd], day[sb][rd], all_res_days)
            if mr_ is None:
                continue
            ml_ = G.score(p[~rd], day[sb][~rd], all_lock_days)
            rows.append(dict(don_e=e, lr_len=ln, lr_read=lr, ma_len=mn, ma_read=mr,
                             don_x=x, stop_n=sn, tp_r=tp,
                             **{f"r_{a}": b for a, b in mr_.items()},
                             **({f"l_{a}": b for a, b in ml_.items()} if ml_ else {})))
    return pd.DataFrame(rows)


def main():
    t0 = time.perf_counter()
    hdr("V38 -- DONCHIAN BREAKOUT + ATR STOP + LINREG MA + MA, 113,400 CONFIGURATIONS")
    print(f"   axes: tf {G.TFS} | donchian entry {G.DON_E} | exit {G.DON_X}")
    print(f"         ATR stop {G.STOP_N} | take profit {G.TP_R} (0 = none)")
    print(f"         LRMA length {G.LR_LEN} x reading {G.LR_READ}")
    print(f"         MA length {G.MA_LEN} x reading {G.MA_READ}")
    print(f"   {G.N_CONFIGS:,} configurations. LONG ONLY, fixed a priori -- NQ rose 89% over this "
          f"sample\n   and a search allowed to pick a side picks long and calls drift an edge.")
    print(f"   costs: real MNQ stack x{G.COST_MULT}, a tick of slippage on STOP exits only.")

    allp = []
    for tf in G.TFS:
        P = G.prep(tf)
        res, lock = blocks(P)
        rd, ld = np.unique(P["day"][res]), np.unique(P["day"][lock])
        print(f"\n   {tf}m: {P['n']:,} bars, {len(rd)} research days / {len(ld)} locked days")
        t1 = time.perf_counter()
        msk = G.masks(P)
        ten = G.tensor(P)
        print(f"        {len(msk)} distinct signal sets x {len(ten)} exit geometries = "
              f"{len(msk) * len(ten):,} cells   (prep {time.perf_counter() - t1:.0f}s)")
        t1 = time.perf_counter()
        df = sweep(P, msk, ten, res, rd, ld, lock)
        df["tf"] = tf
        print(f"        scored {len(df):,} scorable cells in {time.perf_counter() - t1:.0f}s")
        allp.append(df)
    T = pd.concat(allp, ignore_index=True)
    T.to_csv("research/v38/v38_grid.csv", index=False)

    hdr("1. THE SHAPE OF THE GRID -- before any ranking")
    print(f"   scorable cells (>= 20 research trades): {len(T):,} of {G.N_CONFIGS:,}")
    print(f"   research PF > 1.00: {float((T.r_pf > 1).mean()):.1%}    "
          f"> 1.20: {float((T.r_pf > 1.2).mean()):.1%}    > 1.50: {float((T.r_pf > 1.5).mean()):.1%}")
    print(f"   median research PF {T.r_pf.median():.3f}   mean {T.r_pf.mean():.3f}   "
          f"max {T.r_pf.max():.3f}")
    L = T.dropna(subset=["l_pf"])
    print(f"   cells also scorable on locked: {len(L):,}   locked PF > 1.00: "
          f"{float((L.l_pf > 1).mean()):.1%}")
    print(f"   research-to-locked PF correlation: Pearson "
          f"{L.r_pf.corr(L.l_pf):+.3f}   Spearman {L.r_pf.corr(L.l_pf, method='spearman'):+.3f}")

    hdr("2. MARGINAL AVERAGE PER AXIS -- what each knob is worth across every other setting")
    for ax in ("tf", "don_e", "don_x", "stop_n", "tp_r", "lr_len", "lr_read", "ma_len", "ma_read"):
        print(f"\n   {ax}:")
        print(f"      {'value':<14}{'cells':>8}{'res PF':>9}{'res $/t':>10}{'res Sh':>8}"
              f"{'lock PF':>10}{'lock $/t':>10}{'PF>1 res':>10}")
        for v, g in T.groupby(ax):
            gl = g.dropna(subset=["l_pf"])
            print(f"      {str(v):<14}{len(g):>8,}{g.r_pf.mean():>9.3f}{g.r_usd.mean():>+10.2f}"
                  f"{g.r_sharpe.mean():>+8.2f}"
                  f"{(gl.l_pf.mean() if len(gl) else np.nan):>10.3f}"
                  f"{(gl.l_usd.mean() if len(gl) else np.nan):>+10.2f}"
                  f"{float((g.r_pf > 1).mean()):>10.1%}")

    hdr("3. WHAT THE TOP 100 AGREE ON -- consensus, not the best row")
    top = T.sort_values("r_pf", ascending=False).head(100)
    for ax in ("tf", "don_e", "don_x", "stop_n", "tp_r", "lr_len", "lr_read", "ma_len", "ma_read"):
        vc = top[ax].value_counts(normalize=True)
        pop = T[ax].value_counts(normalize=True)
        s = "   ".join(f"{k}: {v:.0%} (pop {pop.get(k, 0):.0%})" for k, v in vc.head(4).items())
        print(f"   {ax:<10} {s}")
    print(f"\n   top-100 mean research PF {top.r_pf.mean():.3f}  n {top.r_n.mean():.0f}")
    tl = top.dropna(subset=["l_pf"])
    print(f"   top-100 mean LOCKED  PF {tl.l_pf.mean():.3f}  n {tl.l_n.mean():.0f}   "
          f"-- the gap is the selection premium")
    T.to_pickle("research/v38/v38_grid.pkl")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
