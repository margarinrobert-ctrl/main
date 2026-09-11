"""A6 -- the two Monte Carlos the branch requires, on the book itself.

A1-A5 bootstrapped the DIFFERENCE between arms and ran two same-procedure random nulls, which
answers "is this allocation better than that one". Neither answers "does the book clear zero" or
"how deep can the drawdown get" -- bootstrap WITH REPLACEMENT for the edge, PERMUTE for the path
(`validate.monte_carlo`'s split), and MC p99 drawdown is the sizing number.
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


def dd(x):
    eq = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(eq) - eq))


def permute(d, n=4000, seed=4):
    """Reshuffle the realised daily series: a DRAWDOWN question only."""
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        out[i] = dd(rng.permutation(d))
    return out


def main():
    X, span, use, cut = prep()
    isr = X.index <= cut

    arms = {
        "walk-fwd all 11, equal": wf(X, span, ALL["equal"]),
        "walk-fwd all 11, riskparity": wf(X, span, ALL["riskparity"]),
        "walk-fwd all 11, meanvar": wf(X, span, ALL["meanvar"]),
        "walk-fwd top 4, equal": wf_select(X, span, topk(4), ALL["equal"]),
        "walk-fwd top 5, riskparity": wf_select(X, span, topk(5), ALL["riskparity"]),
    }
    # the single-fit reserved read, for comparison with A1
    Xr, Xo, sr, so = X.loc[isr], X.loc[~isr], span.loc[isr], span.loc[~isr]
    for nm in ("equal", "meanvar"):
        arms[f"single-fit reserved, {nm}"] = apply_w(Xo, so, ALL[nm](Xr))

    print("=== BOOTSTRAP for the edge (day-block, 4000 draws) -- does the book clear ZERO? ===")
    rows = []
    for nm, d in arms.items():
        bs = C.block_boot(d, n=4000, block=10, seed=1)
        st = C.stats(d)
        rows.append(dict(arm=nm, n=st["n"], total=st["total"], sharpe=st["sharpe"],
                         mean_day=d.mean(),
                         ci_lo=np.percentile(bs, 2.5), ci_hi=np.percentile(bs, 97.5),
                         P_le_0=float(np.mean(bs <= 0))))
    print(pd.DataFrame(rows).round(4).to_string(index=False))

    print("\n=== PERMUTATION for the path (4000 reshuffles) -- the sizing number ===")
    rows = []
    for nm, d in arms.items():
        pm = permute(d)
        r = dd(d)
        rows.append(dict(arm=nm, realised_dd=r, mc_median=np.median(pm),
                         mc_p95=np.percentile(pm, 95), mc_p99=np.percentile(pm, 99),
                         pctile_of_realised=float(np.mean(pm < r)),
                         p99_over_realised=np.percentile(pm, 99) / r if r > 0 else np.nan))
    print(pd.DataFrame(rows).round(3).to_string(index=False))

    print("\n=== worst realised stretches (walk-forward top 5 x risk parity) ===")
    d = arms["walk-fwd top 5, riskparity"]
    eq = np.cumsum(d)
    under = np.maximum.accumulate(eq) - eq
    print(f"max drawdown {under.max():.3f} pct-of-price units; days underwater "
          f"{(under > 1e-9).sum()} of {len(d)} ({100*(under>1e-9).mean():.1f}%)")
    print(f"longest underwater run {max((sum(1 for _ in g) for k, g in __import__('itertools').groupby(under > 1e-9) if k), default=0)} days")


if __name__ == "__main__":
    main()
