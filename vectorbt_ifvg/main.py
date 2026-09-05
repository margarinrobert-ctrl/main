"""
CLI entry point: backtest and/or optimise the IFVG + Liquidity Sweep model.

Examples:
    python -m vectorbt_ifvg.main                 # single backtest, default params
    python -m vectorbt_ifvg.main --optimize      # grid search, then backtest the best
    python -m vectorbt_ifvg.main --optimize --quick
    python -m vectorbt_ifvg.main --days 60 --seed 3
    python -m vectorbt_ifvg.main --csv path/to/nq_1min.csv

If no CSV is given (and none sits in vectorbt_ifvg/data/), a reproducible synthetic
1-minute NQ-like series is generated so the whole thing runs with no data file.
"""

from __future__ import annotations

import argparse

from .data import get_data, load_csv
from .strategy import Params, preset
from .backtest import run_backtest, format_stats
from .optimize import optimize, best_params, DEFAULT_GRID, QUICK_GRID


def main(argv=None):
    ap = argparse.ArgumentParser(description="IFVG + Liquidity Sweep VectorBT backtest")
    ap.add_argument("--csv", help="path to a 1-minute OHLCV CSV (else synthetic)")
    ap.add_argument("--days", type=int, default=60, help="synthetic session count")
    ap.add_argument("--seed", type=int, default=7, help="synthetic RNG seed")
    ap.add_argument("--preset", choices=["default", "robust"], default="default",
                    help="parameter preset ('robust' = cross-seed-validated pure 1:1)")
    ap.add_argument("--optimize", action="store_true", help="run the grid search")
    ap.add_argument("--quick", action="store_true", help="use the small QUICK_GRID")
    ap.add_argument("--min-trades", type=int, default=12, help="opt: min sample size")
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--init-cash", type=float, default=100_000.0)
    args = ap.parse_args(argv)

    if args.csv:
        df, src = load_csv(args.csv), f"csv:{args.csv}"
    else:
        df, src = get_data(days=args.days, seed=args.seed)
    print(f"Loaded {len(df):,} bars ({src}) {df.index[0]} -> {df.index[-1]}\n")

    params = preset(args.preset)

    if args.optimize:
        grid = QUICK_GRID if args.quick else DEFAULT_GRID
        print(f"Grid search over {sum(1 for _ in _count(grid))} combos "
              f"(min_trades={args.min_trades})...\n")
        results = optimize(df, base=params, grid=grid, min_trades=args.min_trades,
                           init_cash=args.init_cash, contracts=args.contracts)
        cols = [c for c in results.columns
                if c in set(grid) | {"n_trades", "total_return_pct",
                                     "profit_factor", "win_rate_pct", "score"}]
        print("\nTop 10 configurations:")
        print(results[cols].head(10).to_string(index=False))
        params = best_params(results, base=params)
        print("\nBacktesting the best configuration:")

    pf, sig, stats = run_backtest(df, params, init_cash=args.init_cash,
                                  contracts=args.contracts)
    print(format_stats(stats, src, params))
    return pf, sig, stats


def _count(grid):
    import itertools
    return itertools.product(*grid.values())


if __name__ == "__main__":
    main()
