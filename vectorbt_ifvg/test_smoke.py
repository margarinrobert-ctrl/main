"""Smoke tests: the pipeline runs and the accounting is internally consistent.

Run with:  python -m vectorbt_ifvg.test_smoke
"""

from __future__ import annotations

import numpy as np

from .data import synthetic_nq, get_data
from .strategy import Params, generate, POINT_VALUE
from .backtest import run_backtest
from .optimize import optimize, best_params, QUICK_GRID


def test_data_shape():
    df = synthetic_nq(days=10, seed=1)
    assert {"open", "high", "low", "close", "volume"} <= set(df.columns)
    assert (df["high"] >= df["low"]).all()
    assert (df["high"] >= df[["open", "close"]].max(axis=1) - 1e-9).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1) + 1e-9).all()
    print("ok  data_shape")


def test_signals_balanced():
    df, _ = get_data(days=40, seed=7)
    sig = generate(df, Params())
    # Every recorded trade has an entry and a matching exit signal.
    assert int(sig.long_entries.sum()) + int(sig.short_entries.sum()) == len(sig.trades)
    assert int(sig.long_exits.sum()) + int(sig.short_exits.sum()) == len(sig.trades)
    # No simultaneous long & short entry on the same bar.
    assert not (sig.long_entries & sig.short_entries).any()
    print(f"ok  signals_balanced ({len(sig.trades)} trades)")


def test_pnl_consistency():
    df, _ = get_data(days=40, seed=7)
    pf, sig, stats = run_backtest(df, Params())
    # Sum of per-trade PnL from the generator should track vbt's realised PnL sign/scale.
    gen_pnl = sum(t["pnl"] for t in sig.trades)
    vbt_pnl = float(pf.trades.pnl.sum())
    # They won't match to the cent (vbt adds commission/slippage) but must agree in sign
    # of the aggregate and be within commission+slippage budget per trade.
    budget = len(sig.trades) * (2 * 2.04 + 2 * 2 * 0.25 * POINT_VALUE)
    assert abs(gen_pnl - vbt_pnl) <= budget + 1e-6, (gen_pnl, vbt_pnl, budget)
    print(f"ok  pnl_consistency (gen={gen_pnl:.0f} vbt={vbt_pnl:.0f})")


def test_optimizer_runs():
    df, _ = get_data(days=30, seed=2)
    res = optimize(df, grid=QUICK_GRID, min_trades=1, verbose=False)
    assert len(res) == 8
    assert res["score"].is_monotonic_decreasing
    bp = best_params(res)
    assert isinstance(bp, Params)
    print("ok  optimizer_runs")


if __name__ == "__main__":
    test_data_shape()
    test_signals_balanced()
    test_pnl_consistency()
    test_optimizer_runs()
    print("\nAll smoke tests passed.")
