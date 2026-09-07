"""The systematic search, and the price of having done it.

Selection uses the RESEARCH half only. The validation quarter breaks ties among finalists. The
holdout quarter is computed here but NEVER used to choose anything -- it exists so the search curve
can be drawn, which is the single most informative diagnostic this repository has:

    take the best config out of K on research, look up where it landed out of sample, sweep K.

On 225,792 initial-balance configurations that curve fell monotonically: a random pick landed at the
51.5th percentile of holdout P&L and the best-of-143,536 at the 13.4th. If the same shape appears
here, the search is a noise generator and the honest answer is a pre-specified rule, not a tuned one.

Usage: python3 research/trend_search.py --workers 3 [--limit N]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from trend_pullback import (COST_NQ, POINT_VALUE_NQ, grid, load, nw_t, run, three_way)

_D = None
_MASKS = None


def _init():
    global _D, _MASKS
    _D = load()
    r_m, v_m, h_m = three_way(_D["sess"])
    # A per-BAR split code, so classifying a trade is one array lookup on its entry index rather
    # than an np.isin scan over every bar. That is the difference between 200 and ~1,300 configs
    # a second, which is what makes the full grid affordable at all.
    code = np.full(len(_D["sess"]), -1, np.int8)
    code[r_m] = 0; code[v_m] = 1; code[h_m] = 2
    _MASKS = code


def _eval(p):
    """Return compact per-split statistics for one configuration."""
    d, code = _D, _MASKS
    side, ti, to, pnl, rm, why = run(d, p)
    if len(pnl) < 60:
        return None
    cc = code[ti]
    ri = cc == 0
    vi = cc == 1
    hi = cc == 2
    if ri.sum() < 30 or hi.sum() < 20:
        return None
    return (
        float(pnl[ri].mean()), float(pnl[ri].sum()), int(ri.sum()), float(nw_t(pnl[ri])),
        float(pnl[vi].mean()) if vi.sum() else np.nan, int(vi.sum()),
        float(pnl[hi].mean()), float(pnl[hi].sum()), int(hi.sum()),
        float(rm[ri].mean()),
    )


def _work(chunk):
    out = []
    for p in chunk:
        r = _eval(p)
        if r is not None:
            out.append((p, r))
    return out


def chunks(it, size):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=0,
                    help="uniform random subsample of the full grid; 0 = every cell")
    ap.add_argument("--seed", type=int, default=20250822)
    ap.add_argument("--out", default="research/trend_search_results.parquet")
    a = ap.parse_args()

    total = sum(1 for _ in grid())
    g = grid()
    if a.sample and a.sample < total:
        # A uniform Bernoulli subsample of the product grid. For a best-of-K curve this is
        # statistically identical to enumerating every cell -- the curve is a property of the
        # DISTRIBUTION of configuration performance, not of which cells were visited -- and it
        # keeps the run to minutes instead of hours.
        rng = np.random.default_rng(a.seed)
        keep = a.sample / total
        g = (p for p in g if rng.random() < keep)
        print(f"  grid has {total:,} cells; sampling ~{a.sample:,} uniformly (seed {a.seed})")
    else:
        print(f"  enumerating all {total:,} grid cells")
    if a.limit:
        g = (p for i, p in enumerate(g) if i < a.limit)

    t0 = time.time()
    rows = []
    params = []
    with Pool(a.workers, initializer=_init) as pool:
        for res in pool.imap_unordered(_work, chunks(g, 2000)):
            for p, r in res:
                params.append(p)
                rows.append(r)
            if len(rows) % 100_000 < 2000 and rows:
                print(f"    {len(rows):,} configs  {time.time()-t0:.0f}s", flush=True)

    cols = ["res_exp", "res_net", "res_n", "res_t", "val_exp", "val_n",
            "hold_exp", "hold_net", "hold_n", "res_er"]
    df = pd.DataFrame(rows, columns=cols)
    for k in params[0]:
        df[k] = [p[k] for p in params]
    df.to_parquet(a.out)
    print(f"\n  {len(df):,} evaluable configurations in {time.time()-t0:.0f}s -> {a.out}")


if __name__ == "__main__":
    main()
