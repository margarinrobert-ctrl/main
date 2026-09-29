"""N5 -- fixed POINT barriers, because that is how the ask was phrased.

100 points is not one geometry. It is 2.35 ATR on US30, 3.24 on NQ and 4.36 on US100, and on US30
alone it was 4.23 ATR in 2016 and 1.10 in 2025 -- so a points grid confounds geometry with market
AND with era (`STUDY_DL50`, `STUDY_US30_SCALP_0711` sections 6-7). That conversion table is printed
FIRST, before any P&L, because it is what decides whether the number means the same thing twice.

DECLARED BEFORE RUNNING: 5 stops x 5 targets x 3 sides = 75 research cells.
`E[max t | pure noise]` over 75 looks is printed beside the 2.802 detection needs.
Only the 100/100 cell is read on the holdout and the forward block.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 200)
SL = [50.0, 75.0, 100.0, 150.0, 200.0]
TP = [0.0, 50.0, 100.0, 150.0, 200.0]
SIDES = ["long", "short", "both"]
HERE = os.path.dirname(os.path.abspath(__file__))


def cell(f, sig, sd, mask, sl, tp, cost):
    tr = N.attach_day(f, N.run(f, sig, sd, stop_pts=sl, tgt_pts=tp, flat_m=960, cost=cost))
    t = tr[mask[tr["sig"].to_numpy()]]
    if len(t) < 25:
        return None
    p = t["pct"].to_numpy()
    return dict(n=len(t), pct=p.mean(), tot=p.sum(),
                pf=t.loc[t.pts > 0, "pts"].sum() / max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9),
                win=(t.pts > 0).mean(), amb=t["amb"].mean(),
                mde=N.mde(p.std(), len(t)), t=p.mean() / max(p.std() / np.sqrt(len(t)), 1e-12),
                _t=t)


def main():
    print("=" * 96)
    print("N5.1  WHAT 100 POINTS IS, PER FEED  -- before any P&L")
    print("=" * 96)
    store = {}
    rows = []
    for name in ("US30L", "US30I", "US100L", "NQ"):
        f = N.load(name, 15)
        rhi, rlo, rn = N.ranges(f)
        store[name] = (f, rhi, rlo)
        sig, sd = N.events(f, rhi, rlo, side="both")
        at = f["atr"].to_numpy()[sig]
        px = f["close"].to_numpy()[sig]
        cost = N.COST[name]
        for sl in SL:
            rows.append(dict(feed=name, sl_pts=sl, in_ATR=round(sl / np.median(at), 2),
                             pct_of_price=round(100 * sl / np.median(px), 3),
                             cost_over_risk=round(cost / sl, 4),
                             be_1to1=round((sl + cost) / (2 * sl), 4)))
    tab = pd.DataFrame(rows)
    print(tab.pivot_table(index="sl_pts", columns="feed", values="in_ATR").to_string())
    print("\n  the same table as cost / risk, and the driftless break-even it implies at 1:1")
    print(tab.pivot_table(index="sl_pts", columns="feed",
                          values="cost_over_risk").round(4).to_string())
    print("\n  A fixed point distance is a DIFFERENT strategy on every feed. On US30 100 points is")
    print("  2.35x the median in-window ATR; on US100 it is 4.36x.")

    print()
    print("=" * 96)
    print("N5.2  THE DECLARED POINTS GRID ON US30 RESEARCH  (75 cells, marginal average only)")
    print("=" * 96)
    f, rhi, rlo = store["US30L"]
    bl = N.blocks(f, "US30L")
    cost = N.COST["US30L"]
    g = []
    for side in SIDES:
        sig, sd = N.events(f, rhi, rlo, side=side)
        for sl in SL:
            for tp in TP:
                r = cell(f, sig, sd, bl["A_research"], sl, tp, cost)
                if r:
                    r.pop("_t")
                    g.append(dict(side=side, sl=sl, tp=tp, **r))
    G = pd.DataFrame(g)
    ncell = len(G)
    print(f"  scorable cells: {ncell};  {100*(G.pct>0).mean():.1f}% profitable")
    print(f"  E[max t | pure noise] over {ncell} looks = {N.e_max_normal(ncell):.3f} "
          f"against the 2.802 detection needs; best |t| achieved = {G['t'].abs().max():.3f}")
    print(f"  cells outside their own MDE: {int((G.pct.abs() > G.mde).sum())} of {ncell}")
    for ax in ("side", "sl", "tp"):
        m = G.groupby(ax)[["pct", "pf", "win", "amb"]].mean()
        m["pct_bp"] = (m.pop("pct") * 100).round(2)
        print(f"\n--- marginal average: {ax} ---")
        print(m.round(4).to_string())

    print()
    print("=" * 96)
    print("N5.3  THE 100 / 100 CELL, one read per block, against a matched random entry")
    print("=" * 96)
    out = []
    for name in ("US30L", "US30I", "US100L", "NQ"):
        f, rhi, rlo = store[name]
        cost = N.COST[name]
        for side in ("long", "both"):
            sig, sd = N.events(f, rhi, rlo, side=side)
            for bn, mask in N.blocks(f, name).items():
                r = cell(f, sig, sd, mask, 100.0, 100.0, cost)
                if r is None:
                    continue
                t = r.pop("_t")
                ne = N.control_entries(f, t, seed=13, n_draw=400, stop_pts=100.0,
                                       tgt_pts=100.0, flat_m=960, cost=cost)
                bo = N.boot_edge(t, n=2000, seed=4)
                be = (100.0 + cost) / 200.0
                out.append(dict(feed=name, block=bn, side=side, n=r["n"],
                                pct=round(r["pct"], 4), pf=round(r["pf"], 3),
                                win=round(r["win"], 3), be=round(be, 3),
                                amb=round(r["amb"], 3),
                                ctl=round(float(np.nanmedian(ne)), 4),
                                p_ent=round(N.pval(r["pct"], ne), 3),
                                boot_le0=round(float((bo <= 0).mean()), 3),
                                mde=round(r["mde"], 4)))
    o = pd.DataFrame(out)
    print(o.to_string(index=False))
    print(f"\n  {len(o)} cells; {int((o.p_ent <= 0.05).sum())} clear p<=0.05 "
          f"against {0.05*len(o):.1f} expected by chance; "
          f"{int((o.pct.abs() > o.mde).sum())} outside their own MDE.")
    print("  `be` is the driftless break-even win rate at 1:1 after cost -- compare it to `win`.")
    o.to_csv(os.path.join(HERE, "n5_points.csv"), index=False)


if __name__ == "__main__":
    main()
