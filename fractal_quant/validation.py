"""Out-of-sample validation (Section 7.4): walk-forward + parameter sweep.

A backtest is hindsight (Section 5). Walk-forward re-selects parameters on a
rolling training window and evaluates *only* on the next out-of-sample block,
then aggregates the OOS pieces into a single equity curve and stat set.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

import numpy as np

from .backtest import _stats, backtest
from .strategy import StrategyParams, generate_signals


def _slice_data(data: dict, a: int, b: int) -> dict:
    return {k: (v[a:b] if k == "date" else np.asarray(v)[a:b])
            for k, v in data.items()}


def evaluate(data: dict, p: StrategyParams, cost_bps: float = 1.0):
    """Run signals + backtest on a data dict, return the BacktestResult."""
    sig = generate_signals(data, p)
    return backtest(sig["ret"], sig["pos"], cost_bps=cost_bps)


def sweep(data: dict, hwins, framaNs, base: StrategyParams,
          cost_bps: float = 1.0):
    """Grid-search Sharpe over Hurst-window x FRAMA-period.

    Returns (grid, best_params) where grid[j][k] is the strategy Sharpe.
    """
    grid = np.full((len(hwins), len(framaNs)), np.nan)
    best, best_sh = base, -np.inf
    for j, hw in enumerate(hwins):
        for k, fn in enumerate(framaNs):
            p = replace(base, hwin=int(hw), framaN=int(fn))
            try:
                res = evaluate(data, p, cost_bps=cost_bps)
                grid[j, k] = res.s.sharpe
                if res.s.sharpe > best_sh:
                    best_sh, best = res.s.sharpe, p
            except Exception:
                pass
    return grid, best


@dataclass
class WalkForwardResult:
    eq_strat: np.ndarray
    eq_bh: np.ndarray
    strat_ret: np.ndarray
    ret: np.ndarray
    s: object
    b: object
    chosen: list
    n_oos: int


def walk_forward(data: dict, base: StrategyParams,
                 train: int = 504, test: int = 126,
                 hwins=(80, 120, 160, 200), framaNs=(10, 16, 24, 32),
                 cost_bps: float = 1.0) -> WalkForwardResult:
    """Rolling walk-forward validation.

    On each step, fit (select best Sharpe params) on ``train`` bars, then apply
    those params to the following ``test`` bars and keep only those OOS returns.
    The OOS pieces are stitched into one equity curve.

    ``train``/``test`` default to ~2y train, ~6mo test.
    """
    n = len(data["close"])
    oos_strat, oos_ret, chosen = [], [], []

    start = 0
    while start + train + test <= n:
        tr = _slice_data(data, start, start + train)
        # parameter selection on the training block only
        _, best = sweep(tr, hwins, framaNs, base, cost_bps=cost_bps)
        chosen.append((data["date"][start + train], best.hwin, best.framaN))

        # evaluate on train+test but keep only the test-block strat returns.
        # signals need warmup history, so generate over the contiguous block
        # ending at the test window and slice the tail.
        blk = _slice_data(data, start, start + train + test)
        sig = generate_signals(blk, best)
        res = backtest(sig["ret"], sig["pos"], cost_bps=cost_bps)
        oos_strat.append(res.strat_ret[train:train + test])
        oos_ret.append(res.ret[train:train + test])

        start += test

    if not oos_strat:
        raise RuntimeError(
            f"Not enough data for walk-forward: need >= {train + test} bars, "
            f"have {n}.")

    strat = np.concatenate(oos_strat)
    ret = np.concatenate(oos_ret)
    eq_s = np.empty(strat.size)
    eq_b = np.empty(ret.size)
    eq_s[0] = eq_b[0] = 10000.0
    for i in range(1, strat.size):
        eq_s[i] = eq_s[i - 1] * (1.0 + strat[i])
        eq_b[i] = eq_b[i - 1] * (1.0 + ret[i])

    return WalkForwardResult(
        eq_strat=eq_s, eq_bh=eq_b, strat_ret=strat, ret=ret,
        s=_stats(strat, eq_s), b=_stats(ret, eq_b),
        chosen=chosen, n_oos=strat.size,
    )
