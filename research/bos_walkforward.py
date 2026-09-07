"""A real walk-forward on BOS/CHoCH — re-selecting parameters, not just slicing fixed ones.

The BOS report's "walk-forward" section was a quarterly breakdown of ONE fixed configuration. That
measures consistency, not selection. A walk-forward re-chooses the parameters on a trailing window
and trades the next one with no knowledge of it, which is what a person running this method would
actually experience. This file does that, rolling and anchored, over two selection spaces:

  SPACE A   timeframe x range filter          (20 cells) -- the choice that produced V2
  SPACE B   EMA x ATR multiple x swing k      (27 cells) at a fixed 30m

Usage: python3 research/bos_walkforward.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from best_versions import _naive_days, daily_from_trades
from bos_choch import prep, run

TRAIN, STEP = 250, 60


def series_for(cfg, cal):
    tf = cfg.pop("_tf", 30)
    d = prep(tf, cfg.get("swing_k", 3), cfg.get("ema_n", 200), 14)
    side, ti, to, pnl, gross, r, why, delay = run(minutes=tf, session="rth_0930_1600", **cfg)
    cfg["_tf"] = tf
    return daily_from_trades(pnl, ti, d["df"].index, cal), len(pnl)


def walk(space, cal, anchored=False):
    """Returns (stitched daily OOS series, list of picks per fold)."""
    mats = {}
    for name, cfg in space.items():
        s, n = series_for(dict(cfg), cal)
        mats[name] = s.to_numpy()
    days = np.arange(len(cal))
    out = np.zeros(len(cal))
    picks = []
    start = 0
    while start + TRAIN + STEP <= len(days):
        tr0 = 0 if anchored else start
        tr = slice(tr0, start + TRAIN)
        te = slice(start + TRAIN, start + TRAIN + STEP)
        best, bv = None, -np.inf
        for name, arr in mats.items():
            v = arr[tr].sum()
            if v > bv:
                bv, best = v, name
        out[te] = mats[best][te]
        picks.append(best)
        start += STEP
    first_oos = TRAIN
    return out, picks, first_oos


def report(name, out, picks, first_oos, cal):
    x = out[first_oos:]
    nz = x[x != 0]
    eq = np.cumsum(x)
    pk = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    dd = (pk - eq).max()
    sh = x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan
    from collections import Counter
    top = Counter(picks).most_common(3)
    print(f"  {name:<34}{len(picks):>7}{len(nz):>9,}{x.sum():>12,.0f}"
          f"{(nz.mean() if len(nz) else np.nan):>11.0f}{sh:>9.2f}{dd:>11,.0f}"
          f"{len(set(picks)):>9}")
    print(f"      most-chosen cells: " + ", ".join(f"{k} x{v}" for k, v in top))


def main() -> None:
    ibd = pd.read_parquet("research/portfolio_daily.parquet")
    cal = _naive_days(pd.to_datetime(ibd.pop("ts")))

    SPACE_A = {f"{tf}m/f{md:g}": dict(_tf=tf, min_ema_dist=md)
               for tf in (5, 15, 30, 60) for md in (0.0, 0.5, 1.0, 1.5, 2.0)}
    SPACE_B = {f"e{e}/a{m:g}/k{k}": dict(_tf=30, ema_n=e, atr_mult=m, swing_k=k, min_ema_dist=1.0)
               for e in (100, 200, 300) for m in (1.0, 2.0, 3.0) for k in (2, 3, 5)}

    print("=" * 108)
    print("WALK-FORWARD — parameters re-chosen on a trailing window, then traded blind")
    print("=" * 108)
    print(f"\n  train {TRAIN} sessions, step {STEP}, selection on net dollars.\n")
    print(f"  {'run':<34}{'folds':>7}{'trades':>9}{'OOS net $':>12}{'$/trade':>11}"
          f"{'Sharpe':>9}{'maxDD $':>11}{'distinct':>9}")
    for label, space in (("SPACE A: timeframe x filter", SPACE_A),
                         ("SPACE B: EMA x ATR x k @30m", SPACE_B)):
        for anch in (False, True):
            out, picks, f0 = walk(space, cal, anchored=anch)
            report(f"{label} ({'anchored' if anch else 'rolling'})", out, picks, f0, cal)

    # the benchmark: the fixed shipped cell over the same out-of-sample span
    fixed, _ = series_for(dict(_tf=30, min_ema_dist=1.0), cal)
    fx = fixed.to_numpy()[TRAIN:]
    nz = fx[fx != 0]
    sh = fx.mean() / fx.std() * np.sqrt(252) if fx.std() > 0 else np.nan
    print(f"\n  {'FIXED V2 (30m/f1.0), same span':<34}{'-':>7}{len(nz):>9,}{fx.sum():>12,.0f}"
          f"{nz.mean():>11.0f}{sh:>9.2f}")
    print("\n  If re-selection beats the fixed cell, the selection procedure adds value.")
    print("  If it does not, the fixed cell is the honest specification and the search is noise.")


if __name__ == "__main__":
    main()
