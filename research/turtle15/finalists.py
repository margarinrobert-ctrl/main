"""Evaluate the search's finalists on everything that was held back.

THE ORDER MATTERS AND IS FIXED. Configurations are ranked on the TRAIN block only (US30 before
2026). Then, once and in this sequence:

  1. US30 2026        -- the judge block, later than every study on this branch
  2. US100 full span  -- a second instrument the search never touched
  3. US100 2026       -- both at once: unseen instrument AND unseen period
  4. selectivity control on each, because the best of 144,000 cells clears any fixed 5% threshold
     roughly 7,200 times by chance
  5. trade-order Monte Carlo, for drawdown shape
  6. the funded-evaluation model, which is the actual question being asked

A finalist that survives 1-3 is interesting. One that survives only 1 has passed a single coin
flip after 144,000 tosses.

RANKING ON TRAIN USES RETURN OVER DRAWDOWN, not profit -- the one structural criterion on this
branch whose in-sample ordering has survived out of sample -- with a trade floor so the winner is
not a six-trade accident.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/turtle15"); sys.path.insert(0, "research/vbt")
import markets, mirror, feats, ablate, fastbars  # noqa: E402
import prop  # noqa: E402

JUDGE_FROM = pd.Timestamp("2026-01-01")


def ctx(path):
    d, si, cut = markets.load_iso(path)
    ts = pd.to_datetime(d["ts"])
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], 20)
    C = mirror.channels(d["h"], d["l"])
    F = feats.build(d, atr, C)
    a0 = mirror.wilder_atr(*[fastbars.bars(15)[k] for k in ("h", "l", "c")], 20)
    cost = (1.72 / (2 * np.nanmedian(a0))) * 2 * np.nanmedian(atr)
    return d, ts, atr, C, F, cost


def mask_for(d, F, row, base):
    g = base.copy()
    if row["adx"] > 0:
        g &= np.nan_to_num(F["adx"] >= row["adx"], nan=False)
    if row["dist"] > 0:
        g &= np.nan_to_num(F["ema_dist_atr"] >= row["dist"], nan=False)
    if row["vol"] > 0:
        g &= np.nan_to_num(F["atr_ratio"] >= row["vol"], nan=False)
    flat = None
    if row["sess"] == 1:
        g &= (d["mod"] >= 360) & (d["mod"] < 720 - 15)
        flat = 720
    return g, flat


def run_row(d, atr, C, F, cost, row, base):
    g, flat = mask_for(d, F, row, base)
    Cx = C if (row["e1"], row["x1"]) == (20, 10) else mirror.channels(
        d["h"], d["l"], int(row["e1"]), 55, int(row["x1"]), 20)
    tp = None if row["tp"] < 0 else float(row["tp"])
    return mirror.run(d, 1, g, atr, Cx, atr_mult=float(row["atr_mult"]),
                      max_units=int(row["units"]), cost=cost, flat_mod=flat, tp_r=tp)


def block(d, ts, atr, C, F, cost, row, when, base_all=None, rng=None, draws=4000):
    """One (config, period) cell: stats plus its selectivity control."""
    m = when if base_all is None else (when & base_all)
    t = run_row(d, atr, C, F, cost, row, m)
    s = ablate.stats(t)
    if s["n"] < 10:
        return s | dict(p=np.nan, ctl=np.nan), t
    b = mirror.run(d, 1, m, atr, C, cost=cost)          # un-gated baseline, same period
    c = ablate.control(b.pnl.to_numpy(), s["n"], draws=draws, rng=rng)
    s["ctl"] = float(c.mean()) if c is not None else np.nan
    s["p"] = float((c >= s["per"]).mean()) if c is not None else np.nan
    return s, t
