"""
Large-sample (law-of-large-numbers) test on synthetic data.

Accumulates ~N trades across many independent synthetic seeds and reports the
converged distribution: win rate, profit factor, mean/expectancy, and a t-stat for
whether mean PnL differs from zero. Memory-safe: one ~120-day chunk is generated and
simulated at a time, trade PnLs are kept, the bars are discarded.

To reach a huge trade count the model is run with its filters OPEN (pure-1:1 exit,
small gap, no killzone/sweep/displacement/daily caps) - i.e. this tests the raw IFVG
inversion entry at scale, not the fully-gated strategy (which is far too selective to
ever produce ~1e6 trades). Both GROSS (does the entry predict direction?) and NET
(after $2.04 commission + 2-tick slippage) figures are reported.

Usage:
    python -m vectorbt_ifvg.big_sample --target 1000000
"""

from __future__ import annotations

import argparse
import math
import time
import numpy as np

from .data import synthetic_nq
from .strategy import generate, Params, POINT_VALUE, MINTICK

COST_PER_ORDER = 2.04 + 2 * MINTICK * POINT_VALUE  # commission + 2-tick slippage

MAXFREQ = dict(use_sweep=False, use_disp=False, use_time=False, use_pd=False,
               use_mss=False, use_double_fvg=False, use_daily_limits=False,
               use_sessions=False, min_gap_ticks=2.0, full_tp_1r=True,
               sweep_lookback=3)


def run(target: int = 1_000_000, days_per_chunk: int = 120, seed0: int = 1):
    p = Params(**MAXFREQ)
    gross = []   # per-trade gross PnL ($)
    net = []     # per-trade net PnL ($, after costs)
    seed = seed0
    t0 = time.time()
    while len(gross) < target:
        df = synthetic_nq(days=days_per_chunk, seed=seed)
        sig = generate(df, p)
        for tr in sig.trades:
            gross.append(tr["pnl"])
            net.append(tr["pnl"] - tr["n_orders"] * COST_PER_ORDER)
        seed += 1
        if seed % 10 == 0 or len(gross) >= target:
            el = time.time() - t0
            rate = len(gross) / el
            eta = (target - len(gross)) / rate if rate > 0 else 0
            print(f"  {len(gross):>9,} trades | {el/60:5.1f} min | "
                  f"{rate:6.0f} trades/s | ETA {eta/60:4.1f} min", flush=True)
    return np.array(gross), np.array(net)


def _stats(x: np.ndarray, label: str):
    n = len(x)
    wins, losses = x[x > 0], x[x < 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")
    mean, sd = x.mean(), x.std(ddof=1)
    tstat = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    print(f"\n=== {label} ({n:,} trades) ===")
    print(f"  win rate      : {len(wins)/n*100:.2f} %")
    print(f"  profit factor : {pf:.3f}")
    print(f"  mean / trade  : ${mean:,.2f}")
    print(f"  std / trade   : ${sd:,.2f}")
    print(f"  total PnL     : ${x.sum():,.0f}")
    print(f"  t-stat (mean!=0): {tstat:+.2f}   (|t|>~2 => significant)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Large-sample synthetic test")
    ap.add_argument("--target", type=int, default=1_000_000)
    ap.add_argument("--days-per-chunk", type=int, default=120)
    args = ap.parse_args(argv)
    print(f"Accumulating >= {args.target:,} trades (max-frequency, pure 1:1)...")
    gross, net = run(args.target, args.days_per_chunk)
    _stats(gross, "GROSS (raw IFVG-inversion entry, no costs)")
    _stats(net, "NET (after $2.04 commission + 2-tick slippage)")


if __name__ == "__main__":
    main()
