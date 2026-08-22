"""The parameter grid, and per-block performance matrices for the validation stage."""
from __future__ import annotations

import itertools
import numpy as np
import pandas as pd

from ib_sim import COMMISSION_PTS, POINT_VALUE, TAKER_SIDE, TICK, simulate

CONST = (TICK, POINT_VALUE, TAKER_SIDE, COMMISSION_PTS)


def build_grid() -> pd.DataFrame:
    """A deliberately wide grid. Width is the thing being measured, not the thing being exploited."""
    rows = list(itertools.product(
        [30, 45, 60, 90],           # ib_minutes
        [10, 25, 40, 50],           # retr_pct
        [60, 70, 80, 100],          # stop_pct
        [1.0, 1.5, 2.0, 3.0],       # rr_mult
        [0, 1, -1],                 # side_mode
        [0, 2],                     # break_buffer (ticks)
    ))
    return pd.DataFrame(rows, columns=["ib_minutes", "retr_pct", "stop_pct", "rr_mult", "side_mode", "break_buffer"])


def run_all(bars, grid: pd.DataFrame):
    """Run every configuration once, returning per-trade R and the exit bar for each."""
    o, h, l, c, sess, mso, atr = bars
    out = []
    for row in grid.itertuples(index=False):
        res = simulate(o, h, l, c, sess, mso, atr,
                       row.ib_minutes, float(row.retr_pct), float(row.stop_pct), float(row.rr_mult),
                       int(row.side_mode), int(row.break_buffer), 0, 1.5, 40.0, *CONST)
        out.append((res[1], res[6], res[5]))   # exit index, R, pnl
    return out


def block_matrix(results, n_bars: int, n_blocks: int, metric: str = "dollars") -> np.ndarray:
    """Per-(block, configuration) performance. The input to CSCV.

    metric="dollars" sums P&L; metric="r" averages R. They do not rank configurations the same way,
    and the difference is large enough to change what CSCV concludes — see STUDY_VECTORBT.md.

    Blocks are contiguous slices of the bar series, so each is a period of calendar time — which is
    what makes the resulting PBO a statement about transfer across time.
    """
    edges = np.linspace(0, n_bars, n_blocks + 1).astype(np.int64)
    M = np.full((n_blocks, len(results)), np.nan)
    for j, (exit_idx, r, pnl) in enumerate(results):
        series = pnl if metric == "dollars" else r
        if len(exit_idx) == 0:
            continue
        b = np.searchsorted(edges, exit_idx, side="right") - 1
        b = np.clip(b, 0, n_blocks - 1)
        for k in range(n_blocks):
            sel = series[b == k]
            if len(sel) >= 5:
                M[k, j] = sel.sum() if metric == "dollars" else sel.mean()
    return M
