"""A7 -- profit factor for the book, at the DAY level, with its own null.

A book has no trade-level profit factor. Eleven legs net against each other inside a day, so the
only PF a portfolio has is over its DAILY series -- sum of up days over |sum of down days| -- and
that number is NOT comparable to a leg's trade-level PF, which is what every other study here
quotes. Both are printed so the difference is visible rather than assumed.

And PF is a ratio a random allocator also earns, so it gets the same 500-draw same-procedure null
as everything else.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alloccore as C  # noqa: E402
from run_a1 import apply_w  # noqa: E402
from run_a2 import prep, ALL  # noqa: E402
from run_a3 import wf  # noqa: E402
from run_a4 import wf_select, topk  # noqa: E402

pd.set_option("display.width", 200)


def pf(x):
    x = np.asarray(x, float)
    up, dn = x[x > 0].sum(), -x[x < 0].sum()
    return float(up / dn) if dn > 0 else np.inf


def main():
    X, span, use, cut = prep()
    isr = X.index <= cut
    Xr, Xo, sr, so = X.loc[isr], X.loc[~isr], span.loc[isr], span.loc[~isr]

    arms = {
        "walk-fwd all 11, equal": wf(X, span, ALL["equal"]),
        "walk-fwd all 11, invvol": wf(X, span, ALL["invvol"]),
        "walk-fwd all 11, riskparity": wf(X, span, ALL["riskparity"]),
        "walk-fwd all 11, minvar": wf(X, span, ALL["minvar"]),
        "walk-fwd all 11, meanvar": wf(X, span, ALL["meanvar"]),
        "walk-fwd top 3, equal": wf_select(X, span, topk(3), ALL["equal"]),
        "walk-fwd top 4, equal": wf_select(X, span, topk(4), ALL["equal"]),
        "walk-fwd top 5, equal": wf_select(X, span, topk(5), ALL["equal"]),
        "walk-fwd top 5, riskparity": wf_select(X, span, topk(5), ALL["riskparity"]),
    }
    for nm in ("equal", "riskparity", "meanvar"):
        arms[f"single-fit reserved, {nm}"] = apply_w(Xo, so, ALL[nm](Xr))
    arms["single-fit RESEARCH, equal"] = apply_w(Xr, sr, ALL["equal"](Xr))

    print("=== 1. DAY-level profit factor (the only PF a book has) ===")
    rows = []
    for nm, d in arms.items():
        n_up, n_dn = int((d > 0).sum()), int((d < 0).sum())
        rows.append(dict(arm=nm, days=len(d), pf=pf(d), win_day=n_up / max(1, n_up + n_dn),
                         mean_up=d[d > 0].mean(), mean_dn=d[d < 0].mean(),
                         sharpe=C.stats(d)["sharpe"], total=C.stats(d)["total"]))
    print(pd.DataFrame(rows).round(4).to_string(index=False))

    print("\n=== 2. against 500 random allocators through the SAME walk-forward procedure ===")
    rnd = []
    for seed in range(500):
        rg = np.random.default_rng(1000 + seed)
        rnd.append(pf(wf(X, span, lambda Z, rg=rg: rg.dirichlet(np.ones(Z.shape[1])))))
    rnd = np.asarray(rnd)
    print(f"random allocator day-PF: p5 {np.percentile(rnd,5):.3f}  median {np.median(rnd):.3f}  "
          f"p95 {np.percentile(rnd,95):.3f}")
    for nm in ("walk-fwd all 11, equal", "walk-fwd all 11, riskparity",
               "walk-fwd all 11, meanvar", "walk-fwd top 4, equal",
               "walk-fwd top 5, riskparity"):
        v = pf(arms[nm])
        print(f"   {nm:30s} {v:.3f} at percentile {100*np.mean(rnd < v):5.1f}")

    print("\n=== 3. random SUBSET of the same size (400 draws, re-drawn each fold) ===")
    for k in (3, 4, 5):
        real = pf(wf_select(X, span, topk(k), ALL["equal"]))
        sub = []
        for seed in range(400):
            rg = np.random.default_rng(5000 + seed)
            sub.append(pf(wf_select(X, span, lambda Xt, rg=rg, k=k:
                                    list(np.asarray(Xt.columns, object)[
                                        rg.choice(Xt.shape[1], size=min(k, Xt.shape[1]),
                                                  replace=False)]))))
        sub = np.asarray(sub)
        print(f"top {k}: PF {real:.3f} at percentile {100*np.mean(sub < real):5.1f}  "
              f"(random median {np.median(sub):.3f})")

    print("\n=== 4. the legs' own TRADE-level PF, for contrast (not comparable to the above) ===")
    legs = C.load()
    rows = []
    for k in use:
        tr = legs[k]["tr"]
        d = pd.to_datetime(tr["sess"].astype(str), format="%Y%m%d")
        for blk, m in (("research", d <= cut), ("reserved", d > cut)):
            p = tr.loc[m, "pct"].to_numpy()
            if len(p) < 20:
                continue
            rows.append(dict(leg=f"{k[0]}/{k[1]}", block=blk, n=len(p), trade_pf=pf(p),
                             win=float((p > 0).mean()), mean=float(p.mean())))
    T = pd.DataFrame(rows)
    print(T.round(4).pivot(index="leg", columns="block",
                           values=["n", "trade_pf", "win"]).round(3).to_string())
    print(f"\nmedian leg trade-PF: research {T[T.block=='research'].trade_pf.median():.3f}  "
          f"reserved {T[T.block=='reserved'].trade_pf.median():.3f}")


if __name__ == "__main__":
    main()
