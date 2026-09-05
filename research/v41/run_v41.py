"""V41 -- the sweep, the ablation the brief implies, and the correlation matrices.

Read in this order, which is the point:
    1. grid SHAPE -- what share is profitable before any ranking
    2. MARGINAL average per axis
    3. THE ABLATION -- does the EMA cross add anything to the Donchian, matched pairwise?
    4. SIGNAL correlation (do the two components see the same bars?) and STRATEGY-RETURN
       correlation among the top cells (a hypothesis count is not a diversification count)
    5. selection, then the locked block read ONCE
    6. robustness: perturbation, walk-forward, bootstrap, cost stress, deflated Sharpe curve

Usage: python3 research/v41/run_v41.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v39")
sys.path.insert(0, "research/v41")
import indicators as I       # noqa: E402
import v38grid as G          # noqa: E402
import v39mc as MC           # noqa: E402
import v41seq as S           # noqa: E402

RESEARCH_FRAC = 0.65


def hdr(t):
    print("\n" + "=" * 128)
    print(t)
    print("=" * 128, flush=True)


def blocks(P):
    u = np.unique(P["day"])
    cut = u[int(len(u) * RESEARCH_FRAC)]
    return P["day"] < cut, P["day"] >= cut


def sweep_tf(tf):
    P = S.prep(tf)
    res, lock = blocks(P)
    rd, ld = np.unique(P["day"][res]), np.unique(P["day"][lock])
    ten = {}
    for x in S.DON_X:
        for sn in S.STOP:
            for tp in S.TP:
                ten[(x, sn, tp)] = G.tensor_stop(P, x, sn, tp, 0)
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    rows = []
    pairs = [(a, b) for a in S.EMA_F for b in S.EMA_S if a < b]
    for (a, b) in pairs:
        for mode in S.EMA_MODE:
            for win in S.WIN:
                inert = (mode == "state" and win != S.WIN[0])
                for e in S.DON_E:
                    for g in S.GATE:
                        sig = S.signal(P, a, b, mode, win, e, g)
                        if len(sig) < 25:
                            continue
                        for (x, sn, tp), (xb, pnl, _w) in ten.items():
                            k = G._lock(sig, xb, pnl, bp, bs)
                            if k < 25:
                                continue
                            p, sb = bp[:k], bs[:k]
                            m = res[sb]
                            mr = G.score(p[m], P["day"][sb][m], rd)
                            if mr is None:
                                continue
                            ml = G.score(p[~m], P["day"][sb][~m], ld)
                            rows.append(dict(
                                tf=tf, ema_f=a, ema_s=b, mode=mode, win=win, don_e=e, don_x=x,
                                stop=sn, tp=tp, gate=g, inert=inert,
                                is_control=(mode == "cross" and win == 0),
                                **{f"r_{kk}": vv for kk, vv in mr.items()},
                                **({f"l_{kk}": vv for kk, vv in ml.items()} if ml else {})))
    return pd.DataFrame(rows), P


def main():
    t0 = time.perf_counter()
    hdr("V41 -- EMA 13/48 CROSS AS FIRST SIGNAL, DONCHIAN AS CONFIRMATION")
    print(f"   nominal cells {S.N_NOMINAL:,}   EFFECTIVE distinct configurations "
          f"{S.N_EFFECTIVE:,}")
    print("   inert axis: under mode 'state' the confirmation-window rungs are one cell, so the")
    print("   multiplicity correction must use the effective count, not the nominal one.")
    print("   built-in ablation: mode 'cross' with win=0 is the DONCHIAN-ALONE control.")
    print("   ATR is WILDER's RMA(20), matching the source script and the Turtle definition --")
    print("   a deliberate departure from this branch's usual ema(TR, n).")
    print("   LONG only, one position at a time, real MNQ costs x1.44, market at the next open.")
    print("\n   DATA: only NQ_1m/NQ_5m survived the last container recycle, so this is NQ ONLY.")
    print("   The cross-market leg is UNAVAILABLE, not skipped -- it needs the feeds re-uploaded.")

    allp = []
    for tf in S.TFS:
        t1 = time.perf_counter()
        df, P = sweep_tf(tf)
        allp.append(df)
        print(f"   {tf}m: {P['n']:,} bars -> {len(df):,} scorable cells "
              f"({time.perf_counter() - t1:.0f}s)")
    T = pd.concat(allp, ignore_index=True)
    T.to_pickle("research/v41/v41_grid.pkl")
    T.to_csv("research/v41/v41_grid.csv", index=False)

    hdr("1. THE SHAPE OF THE GRID")
    E = T[~T.inert]
    print(f"   scorable {len(T):,} of {S.N_NOMINAL:,} nominal   "
          f"non-inert scorable {len(E):,} of {S.N_EFFECTIVE:,} effective")
    print(f"   research PF > 1.00: {float((E.r_pf > 1).mean()):.1%}   "
          f"> 1.20: {float((E.r_pf > 1.2).mean()):.1%}   > 1.50: {float((E.r_pf > 1.5).mean()):.1%}")
    print(f"   median research PF {E.r_pf.median():.3f}   max {E.r_pf.max():.3f}")
    L = E.dropna(subset=["l_pf"])
    print(f"   scorable on locked too: {len(L):,}   locked PF > 1.00: "
          f"{float((L.l_pf > 1).mean()):.1%}")
    print(f"   research-to-locked PF correlation: Pearson {L.r_pf.corr(L.l_pf):+.3f}   "
          f"Spearman {L.r_pf.corr(L.l_pf, method='spearman'):+.3f}")

    hdr("2. MARGINAL AVERAGE PER AXIS -- non-inert cells only")
    for ax in ("tf", "ema_f", "ema_s", "mode", "win", "don_e", "don_x", "stop", "tp", "gate"):
        print(f"\n   {ax}:")
        print(f"      {'value':<12}{'cells':>8}{'res PF':>9}{'res $/t':>10}{'res Sh':>8}"
              f"{'lock PF':>10}{'lock $/t':>10}{'PF>1 res':>10}")
        for v, g in E.groupby(ax):
            gl = g.dropna(subset=["l_pf"])
            print(f"      {str(v):<12}{len(g):>8,}{g.r_pf.mean():>9.3f}{g.r_usd.mean():>+10.2f}"
                  f"{g.r_sharpe.mean():>+8.2f}"
                  f"{(gl.l_pf.mean() if len(gl) else np.nan):>10.3f}"
                  f"{(gl.l_usd.mean() if len(gl) else np.nan):>+10.2f}"
                  f"{float((g.r_pf > 1).mean()):>10.1%}")

    hdr("3. THE ABLATION -- does the EMA cross add anything to the Donchian?")
    print("   Matched PAIRWISE: every (tf, don_e, don_x, stop, tp, gate) geometry compared against")
    print("   its OWN Donchian-alone twin, so nothing but the EMA condition differs.")
    key = ["tf", "don_e", "don_x", "stop", "tp", "gate"]
    ctrl = T[T.is_control].groupby(key).agg(c_r=("r_usd", "mean"), c_l=("l_usd", "mean"),
                                            c_rpf=("r_pf", "mean"), c_lpf=("l_pf", "mean"),
                                            c_n=("r_n", "mean")).reset_index()
    trt = E[~E.is_control]
    J = trt.merge(ctrl, on=key, how="inner")
    J["d_r"] = J.r_usd - J.c_r
    J["d_l"] = J.l_usd - J.c_l
    print(f"\n   {len(J):,} matched pairs")
    print(f"   EMA helps on RESEARCH in {float((J.d_r > 0).mean()):.1%} of pairs "
          f"(mean {J.d_r.mean():+.2f} $/trade)")
    print(f"   EMA helps on LOCKED   in {float((J.d_l > 0).mean()):.1%} of pairs "
          f"(mean {J.d_l.mean():+.2f} $/trade)")
    print(f"   trade count: EMA-confirmed {J.r_n.mean():.0f} vs Donchian alone {J.c_n.mean():.0f} "
          f"({100 * J.r_n.mean() / max(J.c_n.mean(), 1) - 100:+.0f}%)")
    print(f"\n   by mode:")
    for md, g in J.groupby("mode"):
        print(f"      {md:<8} research helps {float((g.d_r > 0).mean()):>6.1%} "
              f"({g.d_r.mean():>+7.2f})   locked helps {float((g.d_l > 0).mean()):>6.1%} "
              f"({g.d_l.mean():>+7.2f})")
    print(f"   by confirmation window (cross mode only):")
    for w, g in J[J["mode"] == "cross"].groupby("win"):
        print(f"      win {w:>3}   research helps {float((g.d_r > 0).mean()):>6.1%} "
              f"({g.d_r.mean():>+7.2f})   locked helps {float((g.d_l > 0).mean()):>6.1%} "
              f"({g.d_l.mean():>+7.2f})   n {g.r_n.mean():>5.0f}")
    J.to_csv("research/v41/v41_ablation.csv", index=False)

    hdr("4. WHAT THE TOP 100 AGREE ON")
    top = E.sort_values("r_pf", ascending=False).head(100)
    for ax in ("tf", "ema_f", "ema_s", "mode", "win", "don_e", "don_x", "stop", "tp", "gate"):
        vc = top[ax].value_counts(normalize=True)
        pop = E[ax].value_counts(normalize=True)
        print(f"   {ax:<9} " + "   ".join(f"{k}: {v:.0%} (pop {pop.get(k, 0):.0%})"
                                          for k, v in vc.head(4).items()))
    tl = top.dropna(subset=["l_pf"])
    print(f"\n   top-100 mean research PF {top.r_pf.mean():.3f}  n {top.r_n.mean():.0f}")
    print(f"   top-100 mean LOCKED  PF {tl.l_pf.mean():.3f}  n {tl.l_n.mean():.0f}   "
          f"<- the gap is the selection premium")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
