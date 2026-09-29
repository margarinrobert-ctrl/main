"""V63 stage F -- is the VWAP acting as SUPPORT, or as a direction filter?

The shipped rule uses `close > VWAP and VWAP rising`, which is a STATE. It never places an order at
the VWAP, never waits for a touch and never requires a pullback. So the question "is it support"
is answerable two ways, and both are run here:

  1. THE READING TABLE. Five VWAP readings were declared before the search, two of them LOCATION
     readings -- a distance FLOOR (at least 0.5 ATR above) and the "not extended" CEILING (above,
     but within 2.0 ATR). Their marginals say what location is worth on this design.
  2. THE ANATOMY. Split the shipped strategy's OWN trades by how far price sat above the VWAP at
     entry. If proximity to the VWAP is what pays, the near quartile earns more. `STUDY_KAMA_ENTRY`
     ran the same test on a moving average and found the tap loses to just taking the trade.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V                                        # noqa: E402
from run_v63b import res_for, geo_index, set_rows          # noqa: E402
from run_v63c import pooled, line                          # noqa: E402
from run_v63d import FINAL                                 # noqa: E402


def main():
    print(__doc__)
    print("=" * 110)
    print("F1. THE FIVE DECLARED READINGS, at the shipped geometry, pooled over the seven blocks")
    print("    that had no part in the search")
    print("=" * 110)
    for read in V.VWAP_READS:
        cell = dict(FINAL, vwap=read)
        if read == "off":
            cell["anchor"], cell["weight"] = "-", "-"
        print(line(f"  {read}", pooled(cell)))
    print("\n  `dist>=0.5` is the FLOOR -- price well ABOVE the VWAP. `0<dist<=2.0` is the")
    print("  not-extended CEILING, the closest thing in the pool to 'buying near support'.")

    print("\n" + "=" * 110)
    print("F2. THE ANATOMY -- the shipped strategy's own trades, split by distance from the VWAP")
    print("    at entry, in ATR. If the VWAP were support, the NEAR quartile would earn more.")
    print("=" * 110)
    allq = []
    for m in V.FEEDSORDER:
        res = res_for(m, int(FINAL["tf"]))
        D = res["D"]
        g = geo_index(res["G"], FINAL)
        sel, _ = set_rows(res, FINAL)
        rows, xb, pts, epx, blk = res["rows"], res["xb"], res["pts"], res["epx"], res["blk"]
        free, rec = -1, []
        vw = D["vw"][(FINAL["anchor"], FINAL["weight"])]
        for k in sel:
            if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or rows[k] <= free:
                continue
            free = xb[k, g]
            i = rows[k]
            d = (D["c"][i] - vw[i]) / max(D["atr"][i], 1e-9)
            rec.append((d, 100.0 * float(pts[k, g]) / epx[k]))
        a = np.array(rec)
        q = pd.qcut(a[:, 0], 4, labels=["Q1 nearest", "Q2", "Q3", "Q4 furthest"])
        t = pd.DataFrame({"d": a[:, 0], "p": a[:, 1], "q": q})
        print(f"  {m}")
        for lab, grp in t.groupby("q", observed=True):
            w = grp["p"] > 0
            print(f"    {lab:12s} n {len(grp):4d}   distance {grp['d'].mean():5.2f} ATR   "
                  f"{grp['p'].mean():+.4f} %/trade   PF "
                  f"{grp.loc[w,'p'].sum()/max(1e-9,-grp.loc[~w,'p'].sum()):5.2f}   win "
                  f"{100*w.mean():5.1f}%")
        allq.append(t)
    t = pd.concat(allq)
    t["q"] = pd.qcut(t["d"], 4, labels=["Q1 nearest", "Q2", "Q3", "Q4 furthest"])
    print("  POOLED")
    for lab, grp in t.groupby("q", observed=True):
        w = grp["p"] > 0
        print(f"    {lab:12s} n {len(grp):4d}   distance {grp['d'].mean():5.2f} ATR   "
              f"{grp['p'].mean():+.4f} %/trade   PF "
              f"{grp.loc[w,'p'].sum()/max(1e-9,-grp.loc[~w,'p'].sum()):5.2f}   win "
              f"{100*w.mean():5.1f}%")
    rho = t["d"].corr(t["p"], method="spearman")
    print(f"    Spearman correlation between distance-from-VWAP at entry and the trade's "
          f"result: {rho:+.4f}")


if __name__ == "__main__":
    main()
