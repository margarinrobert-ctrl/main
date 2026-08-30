"""V42 -- run the sweep. US100 only; US30 and NQ are not touched here."""
from __future__ import annotations

import os, sys, time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle"); sys.path.insert(0, "research/v42")
import v42grid as G      # noqa: E402

OUT = "results/v42"
_P = {}


def _init():
    for tf in G.TFS:
        _P[tf] = G.prep("US100", tf)


def _chunk(args):
    lo, hi = args
    rows = []
    for i, cfg in enumerate(G.configs()):
        if i < lo:
            continue
        if i >= hi:
            break
        if cfg["dup"]:
            continue
        P = _P[cfg["tf"]]
        pnl, risk, tin = G.run_cell(P, cfg)
        s = G.fold_score(P, pnl, risk, tin)
        if s is None:
            continue
        rows.append({**{k: cfg[k] for k in
                        ("tf","entry1","entry2","exit1","exit2","atr_mult","pyr","units",
                         "adx","ext","skip")}, **s})
    return rows


if __name__ == "__main__":
    t0 = time.perf_counter()
    N = G.N_NOMINAL
    W = min(4, os.cpu_count() or 1)
    step = N // (W * 6) + 1
    spans = [(i, min(i + step, N)) for i in range(0, N, step)]
    print(f"US100 sweep: {N:,} nominal cells ({G.N_EFFECTIVE:,} effective) "
          f"over {W} workers in {len(spans)} chunks", flush=True)
    out = []
    with Pool(W, initializer=_init) as pool:
        for j, rows in enumerate(pool.imap_unordered(_chunk, spans), 1):
            out.extend(rows)
            el = time.perf_counter() - t0
            print(f"   chunk {j}/{len(spans)}  scorable so far {len(out):,}  "
                  f"{el:.0f}s elapsed, ~{el/j*(len(spans)-j):.0f}s left", flush=True)
    T = pd.DataFrame(out)
    # narrow before writing: 1.1M rows is 192 MB as float64 CSV and 29 MB as zstd parquet, and
    # the 192 MB form is past GitHub's 100 MB per-file limit -- it failed a push with a 408.
    for c in ("tf", "entry1", "entry2", "exit1", "exit2", "units", "folds_scored",
              "folds_positive", "n"):
        T[c] = T[c].astype("int32")
    for c in ("atr_mult", "pyr", "median_fold", "min_fold", "max_fold", "agg_R", "pf", "pts"):
        T[c] = T[c].astype("float32")
    for c in ("adx", "ext"):
        T[c] = T[c].astype("category")
    os.makedirs(OUT, exist_ok=True)
    T.to_parquet(f"{OUT}/v42_us100_grid.parquet", compression="zstd", index=False)
    print(f"\n{len(T):,} scorable cells written to {OUT}/v42_us100_grid.parquet "
          f"in {time.perf_counter()-t0:.0f}s")
