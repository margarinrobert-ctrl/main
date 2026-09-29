"""x_run5 -- the marginal per axis in EXCESS-OF-NULL units, which is the only unit that isolates
the entry from the exit geometry.

x_run4's mechanism prediction reproduced on all three blocks and two providers: a COIN FLIP with a
0.25 ATR trail reads PF 2.20-2.50. So a raw profit factor is NOT COMPARABLE ACROSS EXIT GEOMETRIES
-- the trail multiplies whatever entry it is attached to. Every one of the 80 declared cells is
therefore given its OWN matched random entry (200 draws, identical exit machinery), and the
marginals are re-read on `pf / ctl_pf` and on `(pts - ctl_pts) * n`.

No new configuration is tried here: these are the same 80 cells with a null attached.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_lib as X  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 280)
STOPS = [30, 50, 75, 100, 150]
TGTS = [100, 150, 200, None]
ARM = "+adx<=20"


def main():
    f = S.load("US30L")
    res = S.blocks(f, "US30L")["A_research"]
    nsess = f.index[res & S.window(f)].normalize().nunique()
    M = X.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    sig, sd = X.signals(f, ARM, res, M)
    chlo = X.chan_low(f, 10, 1)
    elig = S.window(f) & res

    rows = []
    for st in STOPS:
        for tg in TGTS:
            for pol in X.POLICIES:
                kw = dict(stop=st, tgt=tg, policy=pol, chlo=chlo)
                t = X.xwalk(f, sig, sd, **kw)
                r = X.stats(t, nsess, st, tg)
                cp, cf = X.control(f, len(t), t["side"].to_numpy(), elig, n_draw=200,
                                   seed=71, **kw)
                r.update(stop=st, tgt="none" if tg is None else str(tg), policy=pol,
                         ctl_pts=float(np.median(cp)), ctl_pf=float(np.median(cf)),
                         pf_ratio=r["pf"] / float(np.median(cf)),
                         edge=r["pts"] - float(np.median(cp)),
                         p_pts=float(np.mean(cp >= r["pts"])))
                r["excess_total"] = r["edge"] * r["n"]
                rows.append(r)
    G = pd.DataFrame(rows)
    G.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_grid_ctl.csv"),
             index=False)

    print("=== 1. RAW PF vs the PF the SAME EXIT MACHINERY gives a coin flip ===")
    for ax, order in (("policy", X.POLICIES), ("stop", STOPS),
                      ("tgt", [str(t) if t else "none" for t in TGTS])):
        mm = G.groupby(ax).agg(pf=("pf", "mean"), ctl_pf=("ctl_pf", "mean"),
                               pf_ratio=("pf_ratio", "mean"), pts=("pts", "mean"),
                               ctl_pts=("ctl_pts", "mean"), edge=("edge", "mean"),
                               excess_total=("excess_total", "mean"), n=("n", "mean"),
                               ret_dd=("ret_dd", "mean"), mde=("mde", "mean"),
                               p_pts=("p_pts", "mean")).reindex(order)
        print(f"\n  --- marginal by {ax} ---")
        print(mm.round(4).to_string())

    print("\n=== 2. the ranking, in raw PF and in excess-of-null, side by side ===")
    G["rank_pf"] = G.pf.rank(ascending=False)
    G["rank_ratio"] = G.pf_ratio.rank(ascending=False)
    G["rank_xtot"] = G.excess_total.rank(ascending=False)
    print(f"  corr(raw PF, PF/ctl_PF) across 80 cells   {G.pf.corr(G.pf_ratio):+.4f}")
    print(f"  corr(raw PF, excess total)                {G.pf.corr(G.excess_total):+.4f}")
    print(f"  Spearman(rank by PF, rank by excess)      "
          f"{G.rank_pf.corr(G.rank_xtot, method='spearman'):+.4f}")
    print("\n  top 8 by RAW PF:")
    print(G.nlargest(8, "pf")[["stop", "tgt", "policy", "n", "pf", "ctl_pf", "pf_ratio",
                               "pts", "ctl_pts", "edge", "excess_total", "rank_xtot"]]
          .round(3).to_string(index=False))
    print("\n  top 8 by EXCESS TOTAL (the points the ENTRY is worth once the exit is priced):")
    print(G.nlargest(8, "excess_total")[["stop", "tgt", "policy", "n", "pf", "ctl_pf",
                                         "pf_ratio", "pts", "ctl_pts", "edge", "excess_total",
                                         "rank_pf"]].round(3).to_string(index=False))
    print("\n  top 8 by PF RATIO:")
    print(G.nlargest(8, "pf_ratio")[["stop", "tgt", "policy", "n", "pf", "ctl_pf", "pf_ratio",
                                     "pts", "edge", "excess_total", "rank_pf"]]
          .round(3).to_string(index=False))

    print("\n=== 3. the incumbent's own row ===")
    inc = G[(G.stop == 50) & (G.tgt == "150") & (G.policy == "flatten")].iloc[0]
    print(f"  50/150 flatten: PF {inc.pf:.3f}  ctl_PF {inc.ctl_pf:.3f}  ratio {inc.pf_ratio:.3f}"
          f"  edge {inc.edge:+.3f}  excess_total {inc.excess_total:+.1f}"
          f"  rank by PF {int(inc.rank_pf)}/80  rank by ratio {int(inc.rank_ratio)}/80"
          f"  rank by excess {int(inc.rank_xtot)}/80")

    print("\n=== 4. share of the grid whose entry is worth anything once the exit is priced ===")
    print(f"  cells with raw PF > 1                    {float((G.pf > 1).mean()):.1%}")
    print(f"  cells with PF > its own control's PF     {float((G.pf_ratio > 1).mean()):.1%}")
    print(f"  cells with positive excess total         {float((G.excess_total > 0).mean()):.1%}")
    print(f"  cells clearing their control at p<=0.05  {int((G.p_pts <= 0.05).sum())} of 80  "
          f"(4.0 expected by chance)")


if __name__ == "__main__":
    main()
