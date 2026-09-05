"""Every indicator ALONE as a rule, both sides, against a same-size draw from the SAME population.

The control is built ONCE per side: run the engine over EVERY eligible bar with the geometry held
constant, which gives the population of trades that this stop and this exit produce with no
indicator at all. Each signal is then compared with random same-size subsets of that population.

That is the sharper question anyway. It is not "is this better than nothing" -- it is "GIVEN that
you are taking trades with a 2N stop and a 20-bar channel exit, does this indicator pick better
ones than a coin would". An indicator that cannot answer yes is decoration on the exits.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research/v13"); sys.path.insert(0,"research/v8opt")
import eem, v13ctx as V  # noqa: E402

GEO = dict(atr_mult=2.0, max_units=1, tp_r=None, skip_win=False)


def free_channels(C, n, side):
    Cx = dict(C)
    if side > 0:
        Cx["hi1"] = np.full(n, -1e18); Cx["hi2"] = np.full(n, -1e18)
    else:
        Cx["elo1"] = np.full(n, 1e18); Cx["elo2"] = np.full(n, 1e18)
    return Cx


def population(d, atr, C, cost, block, side):
    n = len(atr)
    base = block & np.isfinite(atr) & (atr > 0)
    return eem.run(d, atr, free_channels(C, n, side), base, side=side, cost=cost, **GEO)


def score(d, atr, C, cost, mask, side, pop_pnl, rng, draws=4000, use_donchian=False):
    n = len(atr)
    Cu = C if use_donchian else free_channels(C, n, side)
    t = eem.run(d, atr, Cu, mask, side=side, cost=cost, **GEO)
    s = eem.stats(t)
    if s.get("n", 0) < 40:
        return s | dict(p=np.nan, ctl=np.nan, sh=np.nan)
    k = min(s["n"], len(pop_pnl))
    dr = np.array([rng.choice(pop_pnl, k, replace=False).mean() for _ in range(draws)])
    s["sh"] = V.sharpe(t, d)
    s["ctl"] = float(dr.mean())
    s["p"] = float((dr >= s["per"]).mean())
    return s
