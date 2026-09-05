"""V63 stage C -- the candidate taken apart: drop-one, neighbourhood, costs, folds, Monte Carlo,
hold time and a funded evaluation. Pooled across the three markets, equal-weighted.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V                                                    # noqa: E402
from run_v63 import AXES                                               # noqa: E402
from run_v63b import res_for, geo_index, set_rows, take, stat, boot, entry_control  # noqa: E402

CAND = dict(tf=30, ema="13/34/89", win=30, vwap="above and rising", anchor="roll", weight="flat",
            atrg="off", stop=1.5, trail=2.5, tp=0.0)


def trades(cell, market, cost_mult=1.0):
    res = res_for(market, int(cell["tf"]))
    D, blk, names = res["D"], res["blk"], res["names"]
    g = geo_index(res["G"], cell)
    sel, pool = set_rows(res, cell)
    if cost_mult == 1.0:
        xb, pts = res["xb"], res["pts"]
    else:
        xb, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], res["rows"].astype(np.int64),
                            res["G"]["stop"].to_numpy(float), res["G"]["trail"].to_numpy(float),
                            res["G"]["tp"].to_numpy(float), D["cost"] * cost_mult,
                            D["slip"] * cost_mult, V.HOLD, D["n"])
    tr = take(sel, res["rows"], xb, pts, res["epx"], g, blk)
    return tr, names, D, res, g, sel, pool


def blocks_of(cell, market, cost_mult=1.0):
    tr, names, D, res, g, sel, pool = trades(cell, market, cost_mult)
    return {nm: stat(tr, bi) for bi, nm in enumerate(names)}, D, res, g, sel, pool


def pooled(cell, cost_mult=1.0, oos_only=True):
    """Every block of every market, equal-weighted per BLOCK. `oos_only` drops US100 research,
    which is the only block that chose anything."""
    rows = []
    for m in V.FEEDSORDER:
        b, *_ = blocks_of(cell, m, cost_mult)
        for nm, s in b.items():
            if s is None:
                continue
            if oos_only and m == "US100" and nm == "research":
                continue
            rows.append((m, nm, s))
    if not rows:
        return None
    pct = np.array([s["pct"] for _, _, s in rows])
    n = np.array([s["n"] for _, _, s in rows])
    allp = np.concatenate([s["p"] for _, _, s in rows])
    w = allp > 0
    return dict(blocks=len(rows), pos=int((pct > 0).sum()), mean_block=float(pct.mean()),
                n=int(n.sum()), pct=float(allp.mean()),
                pf=float(allp[w].sum() / max(1e-9, -allp[~w].sum())), rows=rows, p=allp)


def line(lab, r):
    if r is None:
        return f"  {lab:44s}  --"
    return (f"  {lab:44s} blocks {r['pos']}/{r['blocks']} positive   n {r['n']:5d}   "
            f"{r['pct']:+.4f} %/trade   PF {r['pf']:5.2f}   mean of block means "
            f"{r['mean_block']:+.4f}")


def main():
    print(__doc__)
    print("  CANDIDATE: " + ", ".join(f"{k}={v}" for k, v in CAND.items()))
    print("  Long only. 30-minute bars. Enter at the next open when EMA 13 > 34 > 89 has been")
    print("  aligned for at most 30 bars AND price is above a rising anchored average. Stop 1.5")
    print("  ATR, chandelier trail 2.5 ATR from the running high, no target, 480-bar cap.\n")

    print("=" * 118)
    print("C1. DROP-ONE -- every component removed in turn, pooled over the eight blocks that")
    print("    chose nothing (US100 research is excluded: it is the only block that chose)")
    print("=" * 118)
    variants = {
        "the candidate": dict(CAND),
        "  drop the VWAP filter": dict(CAND, vwap="off", anchor="-", weight="-"),
        "  VWAP as `above` only (drop `rising`)": dict(CAND, vwap="above"),
        "  VWAP volume-WEIGHTED instead of flat": dict(CAND, weight="vol"),
        "  VWAP anchored at 09:30 instead of 18:00": dict(CAND, anchor="session"),
        "  drop the trail (fixed stop only)": dict(CAND, trail=0.0),
        "  add a 3 ATR target": dict(CAND, tp=3.0),
        "  enter on the cross bar only (win 0)": dict(CAND, win=0),
        "  a wider 2.5 ATR stop": dict(CAND, stop=2.5),
        "  add the ATR expansion gate": dict(CAND, atrg="atr>=mean"),
    }
    for lab, cell in variants.items():
        print(line(lab, pooled(cell)))

    print("\n" + "=" * 118)
    print("C2. COST STRESS, pooled over the same eight blocks")
    print("=" * 118)
    for cm in (0.0, 1.0, 2.0, 4.0):
        print(line(f"  cost x{cm:.1f}", pooled(CAND, cost_mult=cm)))

    print("\n" + "=" * 118)
    print("C3. HOLD TIME AND THE EXIT PROFILE")
    print("=" * 118)
    for m in V.FEEDSORDER:
        res = res_for(m, int(CAND["tf"]))
        g = geo_index(res["G"], CAND)
        sel, _ = set_rows(res, CAND)
        rows, xb, pts, epx = res["rows"], res["xb"], res["pts"], res["epx"]
        free, hold, pl = -1, [], []
        for k in sel:
            if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or rows[k] <= free:
                continue
            free = xb[k, g]
            hold.append((xb[k, g] - rows[k]) * CAND["tf"])
            pl.append(100.0 * float(pts[k, g]) / epx[k])
        hold, pl = np.array(hold, float), np.array(pl)
        w = pl > 0
        print(f"  {m:7s} n {len(hold):5d}   median hold {np.median(hold):6.0f} min   "
              f"winners {np.median(hold[w]):6.0f}   losers {np.median(hold[~w]):5.0f}   "
              f"under 60 min {100*(hold <= 60).mean():4.1f}%   p90 {np.percentile(hold, 90):6.0f}")

    print("\n" + "=" * 118)
    print("C4. MONTE CARLO on the pooled out-of-sample trades -- bootstrap for the edge,")
    print("    permutation for the path")
    print("=" * 118)
    r = pooled(CAND)
    p = r["p"]
    rng = np.random.default_rng(9)
    mb = np.array([p[rng.integers(0, len(p), len(p))].mean() for _ in range(5000)])
    def dd(x):
        eq = np.cumsum(x)
        return float(np.max(np.maximum.accumulate(eq) - eq))
    perm = np.array([dd(rng.permutation(p)) for _ in range(5000)])
    print(f"  n {len(p)}   mean {p.mean():+.4f} %/trade   P(mean<=0) {np.mean(mb <= 0):.4f}   "
          f"95% CI [{np.percentile(mb,2.5):+.4f}, {np.percentile(mb,97.5):+.4f}]")
    print(f"  realised drawdown {dd(p):.2f}%   permutation median {np.median(perm):.2f}%   "
          f"p99 {np.percentile(perm,99):.2f}%   the realised path sits at percentile "
          f"{np.mean(perm <= dd(p)):.2f}")

    print("\n" + "=" * 118)
    print("C5. PER-BLOCK DETAIL")
    print("=" * 118)
    for m, nm, s in r["rows"]:
        print(f"  {m:7s} {nm:11s} n {s['n']:4d}  {s['pct']:+.4f} %/trade  total {s['tot']:+7.2f}%"
              f"  PF {s['pf']:5.2f}  win {100*s['win']:5.1f}%  maxDD {s['dd']:6.2f}%  "
              f"bootstrap P(mean<=0) {boot(s['p']):.3f}")


if __name__ == "__main__":
    main()
