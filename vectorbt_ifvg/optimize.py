"""
Grid-search optimiser for the IFVG + Liquidity Sweep model.

Sweeps the parameters that most affect the ICT model's behaviour and ranks each
combination by a robust objective. The default objective rewards profit factor and
total return while penalising configurations with too few trades (which over-fit a
handful of lucky setups). Set ``min_trades`` to enforce a sample-size floor.

Usage:
    from vectorbt_ifvg.optimize import optimize, DEFAULT_GRID
    results = optimize(df, grid=DEFAULT_GRID, min_trades=15)
    print(results.head(10))
"""

from __future__ import annotations

import itertools
from dataclasses import replace
import numpy as np
import pandas as pd

from .strategy import Params
from .backtest import run_backtest

# Parameter grid: the knobs that change the trade distribution the most. Keep each
# axis short - the product grows fast (this default is 3*3*3*2*2 = 108 combos).
DEFAULT_GRID: dict[str, list] = {
    "min_gap_ticks": [12.0, 20.0, 32.0],
    "disp_mult": [0.6, 1.0, 1.4],
    "full_tp_1r": [False, True],      # exit style: scale+runner vs pure 1:1
    "sweep_lookback": [3, 5],         # how fast the IFVG must form after the sweep
    "stop_mode": ["IFVG close", "Swing high/low"],
}

# A smaller, faster grid for quick iteration (2*2*2 = 8 combos).
QUICK_GRID: dict[str, list] = {
    "disp_mult": [0.6, 1.0],
    "sweep_lookback": [3, 5],
    "min_gap_ticks": [12.0, 20.0],
}


def _objective(stats: dict, min_trades: int) -> float:
    """Score a run. Higher is better. Disqualify thin samples with -inf.

    Transparent and robust: rank primarily by total return (the thing we care about),
    with profit factor as a small tie-breaker. A trade-count floor stops the search
    from 'winning' on a lucky handful of setups.
    """
    n = stats["n_trades"]
    if n < min_trades:
        return float("-inf")
    pf = stats["profit_factor"]
    if not np.isfinite(pf):
        pf = 0.0
    return stats["total_return_pct"] + 0.1 * min(pf, 5.0)


def optimize(
    df: pd.DataFrame,
    base: Params | None = None,
    grid: dict[str, list] | None = None,
    min_trades: int = 12,
    init_cash: float = 100_000.0,
    contracts: int = 1,
    verbose: bool = True,
) -> pd.DataFrame:
    """Exhaustively evaluate the grid; return a results DataFrame sorted best-first."""
    base = base or Params()
    grid = grid or DEFAULT_GRID
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    rows = []
    for n_done, vals in enumerate(combos, 1):
        overrides = dict(zip(keys, vals))
        p = replace(base, **overrides)
        _, _, stats = run_backtest(df, p, init_cash=init_cash, contracts=contracts)
        score = _objective(stats, min_trades)
        row = {**overrides, **stats, "score": score}
        rows.append(row)
        if verbose:
            tag = " " if np.isfinite(score) else "x"
            print(f"[{n_done:>3}/{len(combos)}] {tag} "
                  + " ".join(f"{k}={overrides[k]}" for k in keys)
                  + f" | trades={stats['n_trades']:>3} "
                  f"ret={stats['total_return_pct']:+6.2f}% pf={stats['profit_factor']:.2f} "
                  f"score={score:.2f}")
    res = pd.DataFrame(rows)
    res = res.sort_values("score", ascending=False).reset_index(drop=True)
    return res


def validate_across_seeds(p: Params, seeds=(7, 1, 2, 3, 42, 100), days: int = 60,
                          init_cash: float = 100_000.0) -> pd.DataFrame:
    """Re-run one config on several synthetic seeds. A real edge should hold up; a
    seed-overfit config will show wild variance / a negative median. Returns a frame
    with per-seed return / win rate / profit factor plus the median row."""
    from .data import synthetic_nq
    rows = []
    for s in seeds:
        df = synthetic_nq(days=days, seed=s)
        _, _, st = run_backtest(df, p, init_cash=init_cash)
        rows.append({"seed": s, "n_trades": st["n_trades"],
                     "return_pct": st["total_return_pct"],
                     "win_rate_pct": st["win_rate_pct"],
                     "profit_factor": st["profit_factor"]})
    res = pd.DataFrame(rows)
    med = res.drop(columns="seed").median(numeric_only=True)
    med["seed"] = "median"
    return pd.concat([res, pd.DataFrame([med])], ignore_index=True)


def best_params(results: pd.DataFrame, base: Params | None = None) -> Params:
    """Reconstruct a Params object from the top-ranked grid row."""
    base = base or Params()
    top = results.iloc[0]
    fields = set(Params().__dataclass_fields__.keys())
    overrides = {k: (top[k].item() if hasattr(top[k], "item") else top[k])
                 for k in results.columns if k in fields}
    return replace(base, **overrides)
