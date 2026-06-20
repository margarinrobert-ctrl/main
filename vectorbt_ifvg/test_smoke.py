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
    # The generator's GROSS per-trade PnL should match vbt's realised PnL up to the
    # commission + slippage budget (which the generator does not model).
    gen_pnl = sum(t["pnl"] for t in sig.trades)
    vbt_pnl = float(pf.trades.pnl.sum())
    n_orders = int(np.isfinite(sig.order_size).sum())
    budget = n_orders * (2.04 + 2 * 0.25 * POINT_VALUE)  # commission + 2-tick slippage
    assert abs(gen_pnl - vbt_pnl) <= budget + 1e-6, (gen_pnl, vbt_pnl, budget)
    # Each entry must be matched by an offsetting set of orders that nets to flat.
    assert abs(float(np.nansum(sig.order_size))) < 1e-9
    print(f"ok  pnl_consistency (gen={gen_pnl:.0f} vbt={vbt_pnl:.0f} budget={budget:.0f})")


def test_orders_net_flat_across_seeds():
    # Regression: an exit and a new entry must never share a bar (order_size holds one
    # fill/bar), otherwise a residual position is marked-to-market and inflates equity.
    from vectorbt_ifvg.data import synthetic_nq
    p = Params(min_gap_ticks=12.0, disp_mult=1.0, sweep_lookback=3,
               stop_mode="Swing high/low")
    for seed in (7, 1, 2, 3, 42, 100):
        df = synthetic_nq(days=40, seed=seed)
        sig = generate(df, p, contracts=1.0)
        resid = float(np.nansum(sig.order_size))
        assert abs(resid) < 1e-9, f"seed {seed}: residual position {resid}"
    print("ok  orders_net_flat_across_seeds")


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
    test_orders_net_flat_across_seeds()
    test_optimizer_runs()
    print("\nAll smoke tests passed.")
