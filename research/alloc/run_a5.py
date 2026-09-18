"""A5 -- stress the one result that cleared its null: does leg selection survive?

A4 found the only thing here that beats its own null decisively -- choosing the legs inside
every training window by their training Sharpe beats a RANDOM SUBSET OF THE SAME SIZE at the
99.5th percentile of 400 draws. Weighting, by contrast, is worth about +0.07 Sharpe and does not
clear a random allocator at p<0.05.

So attack the selection: 2x every feed's assumed cost, the paired difference series, which legs
it actually holds fold by fold, and whether it wins the folds or one fold.
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alloccore as C  # noqa: E402
from run_a2 import ALL, MIN_RES, MIN_RSV  # noqa: E402
from run_a3 import wf  # noqa: E402
from run_a4 import wf_select, topk  # noqa: E402

pd.set_option("display.width", 240)


def prep_from(path):
    with open(path, "rb") as fh:
        legs = pickle.load(fh)
    names = sorted(legs.keys())
    X, span = C.panel(legs, names)
    cut = C.research_cut(legs)
    isr = X.index <= cut
    use = [k for k in names
           if (X.loc[isr, k] != 0).sum() >= MIN_RES and (X.loc[~isr, k] != 0).sum() >= MIN_RSV]
    return X[use], span[use], use


HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    X, span, use = prep_from(os.path.join(HERE, "legs.pkl"))

    # ---- 1. cost stress ---------------------------------------------------------------------
    print("=== 1. 2x every feed's assumed cost, same legs, same procedure ===")
    X2, span2, use2 = prep_from(os.path.join(HERE, "legs_2x.pkl"))
    common = [k for k in use if k in use2]
    print(f"legs at 1x {len(use)}, at 2x {len(use2)}, common {len(common)}")
    rows = []
    for tag, (Z, sp) in (("1x", (X[common], span[common])), ("2x", (X2[common], span2[common]))):
        for nm, pk in (("all", lambda Xt: list(Xt.columns)), ("top4", topk(4)), ("top5", topk(5))):
            for wn in ("equal", "riskparity"):
                d = wf_select(Z, sp, pk, ALL[wn])
                st = C.stats(d)
                rows.append(dict(cost=tag, rule=f"{nm} x {wn}", total=st["total"],
                                 sharpe=st["sharpe"], ret_dd=st["ret_dd"]))
    R = pd.DataFrame(rows)
    print(R.round(3).pivot(index="rule", columns="cost").to_string())

    # ---- 2. the paired difference, block-bootstrapped ---------------------------------------
    print("\n=== 2. paired block bootstrap of the daily difference vs the all-legs equal book ===")
    base = wf(X, span, ALL["equal"])
    for nm, pk, wn in (("top4 x equal", topk(4), "equal"), ("top5 x equal", topk(5), "equal"),
                       ("top5 x riskparity", topk(5), "riskparity"),
                       ("all  x riskparity", lambda Xt: list(Xt.columns), "riskparity")):
        d = wf_select(X, span, pk, ALL[wn])
        n = min(len(d), len(base))
        # compare at MATCHED VOLATILITY, so the difference cannot be leverage
        z = d[:n] * base.std(ddof=1) / d[:n].std(ddof=1) - base[:n]
        bs = C.block_boot(z, seed=3)
        print(f"{nm:20s} vol-matched mean daily diff {z.mean():+.6f}  P(<=0) {np.mean(bs<=0):.3f}"
              f"  95% CI [{np.percentile(bs,2.5):+.6f}, {np.percentile(bs,97.5):+.6f}]")

    # ---- 3. what does it hold? --------------------------------------------------------------
    print("\n=== 3. the legs top-5 actually holds, fold by fold ===")
    d, fd = wf_select(X, span, topk(5), ALL["equal"], ret_folds=True)
    print(fd.to_string(index=False))
    from collections import Counter
    cnt = Counter()
    for h in fd["held"]:
        cnt.update(h.split(","))
    print("\nheld in how many of %d folds:" % len(fd))
    for k, v in cnt.most_common():
        print(f"   {k:18s} {v}")

    # ---- 4. does it win the folds, or one fold? ---------------------------------------------
    print("\n=== 4. per fold, at matched volatility ===")
    _, fb = wf(X, span, ALL["equal"], ret_folds=True)
    rows = []
    for nm, pk, wn in (("top4 x equal", topk(4), "equal"), ("top5 x equal", topk(5), "equal"),
                       ("top5 x riskparity", topk(5), "riskparity")):
        dd, ff = wf_select(X, span, pk, ALL[wn], ret_folds=True)
        s = base.std(ddof=1) / dd.std(ddof=1)
        rows.append(pd.Series((ff["total"].to_numpy() * s) - fb["total"].to_numpy(), name=nm))
    T = pd.concat([fb[["start", "end"]], fb["total"].rename("equal").round(3)] + rows, axis=1)
    print(T.round(3).to_string(index=False))
    for r in rows:
        print(f"   {r.name:20s} folds beaten {int((r > 0).sum())}/{len(r)}")

    # ---- 5. is the pool itself the finding? -------------------------------------------------
    print("\n=== 5. the top-5 book against ALWAYS holding the five legs it most often picks ===")
    fixed = [k for k in use if any(f"{k[0][:4]}/{k[1][:5]}" == n for n, _ in cnt.most_common(5))]
    print("fixed set:", [f"{k[0]}/{k[1]}" for k in fixed])
    if len(fixed) >= 3:
        dfix = wf(X[fixed], span[fixed], ALL["equal"])
        print(f"re-chosen every fold : {pd.Series(C.stats(d)).round(3).to_dict()}")
        print(f"fixed, never re-chosen: {pd.Series(C.stats(dfix)).round(3).to_dict()}")


if __name__ == "__main__":
    main()
