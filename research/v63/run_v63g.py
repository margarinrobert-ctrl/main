"""V63 stage G -- ATR as a REGIME FILTER: 86 declared readings, both directions, on every block.

WHAT THIS BRANCH ALREADY KNOWS, and why the test is built the way it is:

  `STUDY_V28`  ATR as an entry regime filter is NULL on NQ -- 240 declared cells, only 4% clear a
               same-selectivity control at p<=0.05 against a 5% chance rate. On US30 exactly TWO
               cells survived both blocks and both were the same thing: ATR in the bottom fifth of
               its own last 500 bars. Two survivors of 240 is what chance delivers.
  `STUDY_V39`  volatility-state rules INVERT hardest of any family: calm +46.43 research ->
               -9.11 locked, ATR contracting +31.56 -> -20.44.
  `STUDY_V22`  where a STOP goes given heat is a different question from whether calm is a
               profitable ENTRY filter -- do not let one answer the other.

So EVERY reading is run in BOTH directions (a floor and a ceiling), because the conventional
direction has been backwards several times here; every one is scored against a random filter of the
SAME SELECTIVITY over the base's own signals, which is the only null that prices restrictiveness;
and the headline is the SHARE of readings clearing on each block against the 5% chance rate, not
the best row.

THE FAMILY, declared before it ran:
  expansion   atr / sma(atr, N) >= k  and <= k      N in 20/50/100/250, k in 0.9/1.0/1.1/1.2   32
  level       percentile of atr in its own last N   N in 100/250/500, q in 0.2/0.4/0.6/0.8, both 24
  normalised  the same on atr / close                                                          24
  slope       atr > atr[k] and atr < atr[k]         k in 5/10/20                                6
                                                                                       total = 86
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V                                                    # noqa: E402
from run_v63b import res_for, geo_index, set_rows, take, stat, boot    # noqa: E402
from run_v63d import FINAL                                             # noqa: E402

BASE = dict(FINAL, atrg="off")          # the regime filter is tested INSTEAD of the shipped gate
DRAWS = 800
EXP_N, EXP_K = (20, 50, 100, 250), (0.9, 1.0, 1.1, 1.2)
PCT_N, PCT_Q = (100, 250, 500), (0.2, 0.4, 0.6, 0.8)
SLOPE_K = (5, 10, 20)


def readings(D):
    """Every declared reading as a boolean over ALL bars. Causal: a rolling rank includes the
    current bar and nothing after it."""
    atr = pd.Series(D["atr"])
    out = {}
    for N in EXP_N:
        r = (atr / atr.rolling(N).mean()).to_numpy()
        for k in EXP_K:
            out[(f"expansion", f"atr/sma{N} >= {k}")] = np.isfinite(r) & (r >= k)
            out[(f"expansion", f"atr/sma{N} <= {k}")] = np.isfinite(r) & (r <= k)
    for N in PCT_N:
        p = atr.rolling(N).rank(pct=True).to_numpy()
        pn = pd.Series(D["atr"] / D["c"]).rolling(N).rank(pct=True).to_numpy()
        for q in PCT_Q:
            out[("level", f"atr pct{N} >= {q}")] = np.isfinite(p) & (p >= q)
            out[("level", f"atr pct{N} <= {q}")] = np.isfinite(p) & (p <= q)
            out[("normalised", f"atr/price pct{N} >= {q}")] = np.isfinite(pn) & (pn >= q)
            out[("normalised", f"atr/price pct{N} <= {q}")] = np.isfinite(pn) & (pn <= q)
    a = D["atr"]
    for k in SLOPE_K:
        sh = np.concatenate((np.full(k, np.nan), a[:-k]))
        out[("slope", f"atr rising over {k}")] = np.isfinite(sh) & (a > sh)
        out[("slope", f"atr falling over {k}")] = np.isfinite(sh) & (a < sh)
    return out


def control(pool, res, g, blk, nb, rate, draws=DRAWS, seed=163):
    rng = np.random.default_rng(seed)
    out = np.full((draws, nb), np.nan)
    for d in range(draws):
        tr = take(pool[rng.random(len(pool)) < rate], res["rows"], res["xb"], res["pts"],
                  res["epx"], g, blk)
        for bi in range(nb):
            q = [x[1] for x in tr if x[0] == bi]
            out[d, bi] = np.mean(q) if len(q) >= 3 else np.nan
    return out


def main():
    print(__doc__)
    rows = []
    per_market = {}
    for m in V.FEEDSORDER:
        res = res_for(m, int(BASE["tf"]))
        D, blk, names = res["D"], res["blk"], res["names"]
        g = geo_index(res["G"], BASE)
        sel, _ = set_rows(res, BASE)
        base_tr = take(sel, res["rows"], res["xb"], res["pts"], res["epx"], g, blk)
        base = {bi: stat(base_tr, bi) for bi in range(len(names))}
        R = readings(D)
        bars = res["rows"]
        for (fam, name), mask in R.items():
            keep = sel[mask[bars[sel]]]
            if len(keep) < 30:
                continue
            rate = len(keep) / len(sel)
            tr = take(keep, res["rows"], res["xb"], res["pts"], res["epx"], g, blk)
            ctl = control(sel, res, g, blk, len(names), rate)
            for bi, nm in enumerate(names):
                s = stat(tr, bi)
                b = base[bi]
                if s is None or b is None:
                    continue
                c = ctl[:, bi][np.isfinite(ctl[:, bi])]
                rows.append(dict(market=m, block=nm, family=fam, reading=name, keep=rate,
                                 n=s["n"], pct=s["pct"], pf=s["pf"], base_pct=b["pct"],
                                 base_n=b["n"], edge=s["pct"] - b["pct"],
                                 p=float(np.mean(c >= s["pct"])) if len(c) else np.nan))
        per_market[m] = base
        print(f"  .. {m} done")
    d = pd.DataFrame(rows)
    d.to_csv("results/v63/atr_regime.csv", index=False)

    oos = d[~((d["market"] == "US100") & (d["block"] == "research"))]
    print("\n" + "=" * 112)
    print("G1. THE SHARE THAT CLEARS -- against a random filter of the SAME selectivity.")
    print("    Chance is 5%. Read this before any row of the table.")
    print("=" * 112)
    for blkname, sub in d.groupby(["market", "block"]):
        n = len(sub)
        k = int((sub["p"] <= 0.05).sum())
        print(f"  {blkname[0]:7s} {blkname[1]:11s} {k:3d} of {n:3d} readings clear "
              f"({100*k/max(n,1):5.1f}%, chance 5.0%)   beat the no-regime baseline: "
              f"{100*(sub['edge'] > 0).mean():5.1f}%")
    print(f"\n  ALL BLOCKS THAT CHOSE NOTHING: {int((oos['p'] <= 0.05).sum())} of {len(oos)} "
          f"({100*(oos['p'] <= 0.05).mean():.1f}%) clear at p<=0.05; "
          f"{100*(oos['edge'] > 0).mean():.1f}% beat the no-regime baseline (chance 50%).")

    print("\n" + "=" * 112)
    print("G2. BY FAMILY AND DIRECTION -- mean edge over the no-regime baseline, %/trade")
    print("=" * 112)
    oos = oos.copy()
    oos["dir"] = np.where(oos["reading"].str.contains(">=|rising"), "floor / rising",
                          "ceiling / falling")
    for (fam, dr), sub in oos.groupby(["family", "dir"]):
        print(f"  {fam:11s} {dr:17s} {len(sub):4d} cells   mean edge {sub['edge'].mean():+.4f}   "
              f"beats baseline {100*(sub['edge'] > 0).mean():5.1f}%   clears "
              f"{100*(sub['p'] <= 0.05).mean():5.1f}%   keeps {100*sub['keep'].mean():5.1f}%")

    print("\n" + "=" * 112)
    print("G3. CONSISTENCY -- readings positive on EVERY block that chose nothing, ranked by")
    print("    their mean edge. A reading has to survive 7 blocks to appear here.")
    print("=" * 112)
    g = oos.groupby("reading").agg(blocks=("edge", "size"), pos=("edge", lambda x: (x > 0).sum()),
                                   edge=("edge", "mean"), keep=("keep", "mean"),
                                   clears=("p", lambda x: (x <= 0.05).sum()),
                                   pmin=("p", "min"))
    g = g[(g["blocks"] >= 7) & (g["pos"] == g["blocks"])].sort_values("edge", ascending=False)
    if not len(g):
        print("  NONE. Not one of the 86 readings is positive on every block that chose nothing.")
    for name, r in g.head(15).iterrows():
        print(f"  {name:26s} {int(r['pos'])}/{int(r['blocks'])} blocks   edge {r['edge']:+.4f}   "
              f"keeps {100*r['keep']:5.1f}%   clears its control on {int(r['clears'])}   "
              f"best p {r['pmin']:.3f}")

    print("\n" + "=" * 112)
    print("G4. THE SHIPPED GATE (atr >= its own 50-bar mean) IN THIS TABLE")
    print("=" * 112)
    sub = d[d["reading"] == "atr/sma50 >= 1.0"]
    for _, r in sub.iterrows():
        tag = "IS " if (r["market"] == "US100" and r["block"] == "research") else "OOS"
        print(f"  {r['market']:7s} {r['block']:11s} {tag} n {int(r['n']):4d} keeps "
              f"{100*r['keep']:5.1f}%   {r['pct']:+.4f} against a no-regime baseline of "
              f"{r['base_pct']:+.4f}   edge {r['edge']:+.4f}   control p {r['p']:.3f}")


if __name__ == "__main__":
    main()
