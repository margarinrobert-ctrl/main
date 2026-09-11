"""The experiment: every declared condition, both triggers, both geometries, six feed-timeframes."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sr_core as S  # noqa: E402

OUT = "results/scalpreq"


def one(D, trig_name, trig, geom_name):
    stop, tp, hold = S.GEOM[geom_name]
    n = D["n"]
    m = trig.copy()
    m[:300] = False
    m[-(hold + 6):] = False
    m &= np.isfinite(D["atr"]) & (D["atr"] > 0)
    rows = np.flatnonzero(m)
    if len(rows) < 50:
        return []
    pts, xb = S.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64),
                     stop, tp, hold, D["cost"], D["slip"], n)
    epx = D["o"][np.minimum(rows + 1, n - 1)]
    names = list(D["blocks"].keys())
    blk = np.full(n, -1, np.int64)
    for i, nm in enumerate(names):
        blk[np.asarray(D["blocks"][nm], bool)] = i
    base = S.lock(rows, np.arange(len(rows)), pts, xb, epx, blk)
    C = S.conditions(D)
    allbars = np.arange(300, n - hold - 6)
    out = []
    for (fam, cname), mask in C.items():
        on_trig = float(mask[rows].mean())
        on_all = float(mask[allbars].mean())
        keep = np.flatnonzero(mask[rows])
        if len(keep) < 20:
            continue
        tr = S.lock(rows, keep, pts, xb, epx, blk)
        for bi, nm in enumerate(names):
            bp = np.array([x[1] for x in base if x[0] == bi])
            fp = np.array([x[1] for x in tr if x[0] == bi])
            if len(bp) < 10 or len(fp) < 10:
                continue
            out.append(dict(market=D["market"], tf=D["tf"], trigger=trig_name, geom=geom_name,
                            block=nm, family=fam, cond=cname, on_trig=on_trig, on_all=on_all,
                            lift=on_trig / max(on_all, 1e-9), n=len(fp), pct=float(fp.mean()),
                            base_n=len(bp), base_pct=float(bp.mean()),
                            edge=float(fp.mean() - bp.mean())))
    return out


def main():
    print(__doc__)
    print(S.__doc__)
    rows = []
    base_rows = []
    for market, tf in S.FEEDS:
        D = S.build(market, tf)
        T = S.triggers(D)
        for tname, trig in T.items():
            for g in S.GEOM:
                r = one(D, tname, trig, g)
                rows += r
                if r:
                    b = r[0]
                    for x in {(y["block"], y["base_n"], y["base_pct"]) for y in r}:
                        base_rows.append(dict(market=market, tf=tf, trigger=tname, geom=g,
                                              block=x[0], n=x[1], pct=x[2]))
        print(f"  .. {market} {tf}m done")
    d = pd.DataFrame(rows)
    b = pd.DataFrame(base_rows).drop_duplicates()
    d.to_csv(f"{OUT}/conditions.csv", index=False)
    b.to_csv(f"{OUT}/base.csv", index=False)

    print("\n" + "=" * 116)
    print("1. THE UNFILTERED TRIGGER AT BOTH GEOMETRIES -- before any indicator is added")
    print("=" * 116)
    print(f"  {'trigger':32s} {'geometry':8s} {'blocks':>7s} {'blocks +':>9s} {'n':>7s} "
          f"{'%/trade':>9s}")
    for (t, g), s in b.groupby(["trigger", "geom"]):
        tot = (s["n"] * s["pct"]).sum() / max(s["n"].sum(), 1)
        print(f"  {t:32s} {g:8s} {len(s):7d} {int((s['pct']>0).sum()):9d} "
              f"{int(s['n'].sum()):7d} {tot:+9.4f}")
    print("\n  The scalp geometry is a 0.75 ATR stop, a 1.5 ATR target and a 24-bar cap; the swing")
    print("  is a 2.5 ATR stop, no target and a 480-bar cap. Same triggers, same bars, same costs.")

    print("\n" + "=" * 116)
    print("2. BASE RATE ON THE TRIGGER'S OWN BARS -- what fraction of the signals each condition")
    print("   would even remove. Pooled over the six feed-timeframes.")
    print("=" * 116)
    br = d.groupby(["family", "cond", "trigger"]).agg(on_trig=("on_trig", "mean"),
                                                      on_all=("on_all", "mean"),
                                                      lift=("lift", "mean")).reset_index()
    for trig in br["trigger"].unique():
        print(f"\n  --- {trig}")
        s = br[br["trigger"] == trig].sort_values("on_trig", ascending=False)
        for _, r in s.iterrows():
            flag = ("  <-- INERT, removes under 10%" if r["on_trig"] > 0.90 else
                    ("  <-- selective" if r["on_trig"] < 0.45 else ""))
            print(f"    {r['family']:9s} {r['cond']:30s} passes {100*r['on_trig']:5.1f}% of "
                  f"signals vs {100*r['on_all']:5.1f}% of bars   lift {r['lift']:4.2f}{flag}")

    print("\n" + "=" * 116)
    print("3. WHAT EACH CONDITION CONTRIBUTES -- percent of price per trade over the unfiltered")
    print("   trigger, at SCALP geometry and at SWING geometry, and the share of blocks improved")
    print("=" * 116)
    g = d.groupby(["family", "cond", "geom"]).agg(edge=("edge", "mean"),
                                                  helps=("edge", lambda x: (x > 0).mean()),
                                                  cells=("edge", "size"),
                                                  keep=("on_trig", "mean")).reset_index()
    piv = g.pivot_table(index=["family", "cond"], columns="geom",
                        values=["edge", "helps", "cells"]).reset_index()
    piv.columns = ["family", "cond", "cells_scalp", "cells_swing", "edge_scalp", "edge_swing",
                   "helps_scalp", "helps_swing"]
    piv["keep"] = g.groupby(["family", "cond"])["keep"].mean().to_numpy()
    piv = piv.sort_values("edge_swing", ascending=False)
    print(f"  {'family':9s} {'condition':30s} {'keeps':>6s} | {'SCALP edge':>10s} {'helps':>6s} | "
          f"{'SWING edge':>10s} {'helps':>6s}")
    for _, r in piv.iterrows():
        print(f"  {r['family']:9s} {r['cond']:30s} {100*r['keep']:5.1f}% | "
              f"{r['edge_scalp']:+10.4f} {100*r['helps_scalp']:5.0f}% | "
              f"{r['edge_swing']:+10.4f} {100*r['helps_swing']:5.0f}%")
    piv.to_csv(f"{OUT}/summary.csv", index=False)

    print("\n" + "=" * 116)
    print("4. BY FAMILY")
    print("=" * 116)
    fam = piv.groupby("family").agg(n=("cond", "size"), sc=("edge_scalp", "mean"),
                                    sh=("helps_scalp", "mean"), sw=("edge_swing", "mean"),
                                    wh=("helps_swing", "mean"), keep=("keep", "mean"))
    print(f"  {'family':10s} {'conds':>6s} {'keeps':>7s} | {'SCALP edge':>11s} {'helps':>7s} | "
          f"{'SWING edge':>11s} {'helps':>7s}")
    for k, r in fam.sort_values("sw", ascending=False).iterrows():
        print(f"  {k:10s} {int(r['n']):6d} {100*r['keep']:6.1f}% | {r['sc']:+11.4f} "
              f"{100*r['sh']:6.0f}% | {r['sw']:+11.4f} {100*r['wh']:6.0f}%")

    print("\n" + "=" * 116)
    print("5. THE SHORT LIST -- conditions that improve on a MAJORITY of cells at BOTH geometries")
    print("=" * 116)
    sl = piv[(piv["helps_scalp"] > 0.5) & (piv["helps_swing"] > 0.5)].sort_values(
        "edge_scalp", ascending=False)
    if not len(sl):
        print("  NONE.")
    for _, r in sl.iterrows():
        print(f"  {r['family']:9s} {r['cond']:30s} keeps {100*r['keep']:5.1f}%   scalp "
              f"{r['edge_scalp']:+.4f} ({100*r['helps_scalp']:.0f}%)   swing "
              f"{r['edge_swing']:+.4f} ({100*r['helps_swing']:.0f}%)")
    print(f"\n  {len(sl)} of {len(piv)} conditions. Chance, if each cell were a coin flip, would")
    print("  put roughly a quarter of them here.")


if __name__ == "__main__":
    main()
