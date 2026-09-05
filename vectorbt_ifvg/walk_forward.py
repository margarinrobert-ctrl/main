"""
Rolling walk-forward validation on real data.

For each consecutive (train_year -> test_year) pair: grid-optimise on the train year,
then apply the single best config to the *untouched* test year and record only the
out-of-sample (OOS) result. Pooling every OOS year gives the honest picture - the
number you'd have actually earned trading the optimiser's choice forward.

This is the rigorous version of "most profitable": in-sample cherry-picking is
excluded by construction.

Usage (expects a multi-year CSV in data/, e.g. from fetch_nas100.py):
    python -m vectorbt_ifvg.walk_forward
"""

from __future__ import annotations

import itertools
from dataclasses import replace
import numpy as np
import pandas as pd

from .data import get_data
from .strategy import Params
from .backtest import run_backtest

COST_PER_ORDER = 2.04 + 2 * 0.25 * 20.0  # commission + 2-tick slippage (NQ econ)

# Small, deliberately coarse grid (pure 1:1 exit) to limit overfitting surface.
WF_GRID = {
    "disp_mult": [0.6, 1.0, 1.4],
    "stop_mode": ["IFVG close", "Swing high/low"],
}
WF_BASE = Params(full_tp_1r=True, min_gap_ticks=12.0, sweep_lookback=3)


def _net_trades(sig):
    return np.array([t["pnl"] - t["n_orders"] * COST_PER_ORDER for t in sig.trades])


def _agg(net: np.ndarray, init_cash=100_000.0) -> dict:
    if len(net) == 0:
        return dict(n=0, ret=np.nan, win=np.nan, pf=np.nan)
    wins, losses = net[net > 0], net[net < 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")
    return dict(n=len(net), ret=net.sum() / init_cash * 100,
                win=len(wins) / len(net) * 100, pf=pf)


def optimise_year(df_train: Params, base=WF_BASE, grid=WF_GRID, min_trades=15) -> Params:
    keys = list(grid)
    best, best_score = None, -1e18
    for vals in itertools.product(*grid.values()):
        p = replace(base, **dict(zip(keys, vals)))
        _, _, s = run_backtest(df_train, p)
        if s["n_trades"] >= min_trades and s["total_return_pct"] > best_score:
            best_score, best = s["total_return_pct"], p
    return best or base


def walk_forward(df: pd.DataFrame):
    years = sorted({ts.year for ts in df.index})
    pairs = [(y, y + 1) for y in years if (y + 1) in years]
    print(f"Years: {years}  |  folds: {pairs}\n")
    print(f"{'train→test':<14}{'cfg(disp/stop)':<22}{'OOS trades':>10}"
          f"{'OOS ret%':>10}{'win%':>8}{'PF':>7}")
    print("-" * 71)

    pooled = []
    fold_returns = []
    for tr, te in pairs:
        dtr = df[df.index.year == tr]
        dte = df[df.index.year == te]
        bp = optimise_year(dtr)
        _, sig, s = run_backtest(dte, bp)
        net = _net_trades(sig)
        pooled.append(net)
        fold_returns.append(s["total_return_pct"])
        cfg = f"{bp.disp_mult}/{bp.stop_mode[:4]}"
        print(f"{tr}→{te:<9}{cfg:<22}{s['n_trades']:>10}{s['total_return_pct']:>10.2f}"
              f"{s['win_rate_pct']:>8.1f}{s['profit_factor']:>7.2f}")

    allnet = np.concatenate(pooled) if pooled else np.array([])
    agg = _agg(allnet)
    compounded = np.prod([1 + r / 100 for r in fold_returns]) - 1
    print("-" * 71)
    print(f"\nPOOLED OUT-OF-SAMPLE ({agg['n']} trades across {len(pairs)} test years):")
    print(f"  sum of OOS returns : {agg['ret']:+.2f}%   compounded: {compounded*100:+.2f}%")
    print(f"  win rate           : {agg['win']:.1f}%")
    print(f"  profit factor      : {agg['pf']:.2f}")
    print(f"  avg net / trade    : ${allnet.mean():,.2f}" if agg['n'] else "")
    return agg


if __name__ == "__main__":
    df, src = get_data()
    print(f"Data: {src}  ({len(df):,} bars, {df.index[0]} .. {df.index[-1]})\n")
    walk_forward(df)
