"""The maximum-width search, run as an experiment rather than as a way to pick parameters.

This repository has already measured wide search as harmful (STUDY_SEARCH_CURVE.md,
STUDY_VECTORBT.md). Running 225,792 configurations is therefore not an attempt to find the best
one — it is a test of what a maximum-width search actually delivers on data that selection never
touched.

The protocol:
  RESEARCH  first 60% of bars   — the only data selection is allowed to see
  VALIDATE  next 20%            — used once, to rank the finalists
  LOCKED    last 20%            — touched exactly once, at the very end

Selection is on DOLLARS, not mean R: STUDY_VECTORBT.md showed the R objective converges on
small-denominator configurations and hides the failure.

Usage: python3 research/mega_sweep.py [--out results.npz]
"""
from __future__ import annotations

import itertools
import sys
import time

import numpy as np
import pandas as pd
from numba import njit, prange

sys.path.insert(0, "research")
from ib_sim import COMMISSION_PTS, POINT_VALUE, TAKER_SIDE, TICK, simulate
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice

OUT = "results/mega/mega.npz"
for i, a in enumerate(sys.argv):
    if a == "--out":
        OUT = sys.argv[i + 1]

AXES = {
    "ib_minutes":   [15, 30, 45, 60, 75, 90, 120],
    "retr_pct":     [0, 10, 20, 25, 33, 40, 50, 60],
    "stop_pct":     [50, 60, 70, 80, 90, 100, 120, 150],
    "rr_mult":      [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0],
    "side_mode":    [0, 1, -1],
    "break_buffer": [0, 2, 4],
    "exit_mso":     [90, 120, 150, 180, 240, 300, 389],
}


def main() -> None:
    seg = session_slice(load_bars("data/NQ_1m.csv"), 570, 960)
    mod = minute_of_day(seg.index)
    o, h, l, c = (seg[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    sess = session_index(seg.index, 570)
    mso = minutes_since_open(mod, 570).astype(np.int64)
    atr = np.zeros(len(seg))
    n = len(seg)
    r_end, v_end = int(n * 0.60), int(n * 0.80)

    names = list(AXES)
    combos = np.array(list(itertools.product(*(AXES[k] for k in names))), dtype=np.float64)
    total = len(combos)
    print(f"{total:,} configurations over {n:,} bars")
    print(f"  research < {r_end:,} | validate < {v_end:,} | LOCKED >= {v_end:,}\n")

    cols = {k: np.zeros(total) for k in
            ("n_res", "n_val", "n_hold", "d_res", "d_val", "d_hold", "r_res", "r_val", "r_hold")}

    t0 = time.perf_counter()
    for j in range(total):
        ibm, retr, stop, rr, side, buf, ex = combos[j]
        res = simulate(o, h, l, c, sess, mso, atr,
                       int(ibm), retr, stop, rr, int(side), int(buf), 0, 1.5, 40.0, 0, 10.0, 50.0, int(ex),
                       TICK, POINT_VALUE, TAKER_SIDE, COMMISSION_PTS)
        ei, pnl, rr_ = res[1], res[5], res[6]
        if len(ei) == 0:
            continue
        m_res, m_val = ei < r_end, (ei >= r_end) & (ei < v_end)
        m_hold = ei >= v_end
        for tag, m in (("res", m_res), ("val", m_val), ("hold", m_hold)):
            k = int(m.sum())
            cols[f"n_{tag}"][j] = k
            if k:
                cols[f"d_{tag}"][j] = pnl[m].sum()
                cols[f"r_{tag}"][j] = rr_[m].mean()
        if j and j % 20000 == 0:
            el = time.perf_counter() - t0
            print(f"  {j:>7,} / {total:,}  {el:6.0f}s elapsed, ~{el/j*(total-j):5.0f}s left")

    el = time.perf_counter() - t0
    print(f"\n  done in {el:.0f}s ({total/el:,.0f} configs/sec)")

    grid = pd.DataFrame(combos, columns=names)
    for k, v in cols.items():
        grid[k] = v
    np.savez_compressed(OUT, **{k: grid[k].to_numpy() for k in grid.columns})
    print(f"  saved -> {OUT}")


if __name__ == "__main__":
    main()
