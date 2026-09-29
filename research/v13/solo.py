"""Every indicator ALONE as a trading rule, both sides, each against its own matched control.

AN IC AND A TRADING RULE ARE DIFFERENT OBJECTS. IC measures rank association with the next h bars;
a rule with a 2N stop and a channel exit has convexity the IC cannot see. So every signal is run as
an actual rule here, and every one is scored against a RANDOM BAR carrying the SAME side, the same
stop, the same exit and the same trade count -- which is the only comparison that answers "does
this indicator know anything".

The exits are held constant across every row on purpose: 2.0N stop, 20-bar channel, ONE unit, NO
take profit. That geometry is not a choice made here, it is what three earlier studies on this
branch converged on, and holding it fixed is what makes the ROWS comparable to each other.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research/v13"); sys.path.insert(0,"research/v8opt")
import eem, v13ctx as V  # noqa: E402

GEO = dict(atr_mult=2.0, max_units=1, tp_r=None, skip_win=False)


def free_channels(C, n, side):
    """Channels that always trigger, so a mask alone decides the entries."""
    Cx = dict(C)
    if side > 0:
        Cx["hi1"] = np.full(n, -1e18); Cx["hi2"] = np.full(n, -1e18)
    else:
        Cx["elo1"] = np.full(n, 1e18); Cx["elo2"] = np.full(n, 1e18)
    return Cx


def solo(d, atr, C, cost, mask, side, draws=200, rng=None, use_donchian=False):
    """One signal, one side: its stats and its p against a random bar with the same geometry."""
    rng = rng or np.random.default_rng(0)
    n = len(atr)
    Cu = C if use_donchian else free_channels(C, n, side)
    t = eem.run(d, atr, Cu, mask, side=side, cost=cost, **GEO)
    s = eem.stats(t)
    if s["n"] < 40:
        return s | dict(p=np.nan, ctl=np.nan, sh=np.nan)
    elig = np.flatnonzero(mask.dtype == bool and np.isfinite(atr) & (atr > 0))
    pool = np.flatnonzero(np.isfinite(atr) & (atr > 0) & _block_of(mask))
    Cf = free_channels(C, n, side)
    ctl = []
    for _ in range(draws):
        pk = np.zeros(n, bool); pk[rng.choice(pool, min(s["n"], len(pool)), replace=False)] = True
        q = eem.run(d, atr, Cf, pk, side=side, cost=cost, **GEO)
        if len(q) > 20:
            ctl.append(q.pnl.mean())
    ctl = np.array(ctl)
    s["sh"] = V.sharpe(t, d)
    s["ctl"] = float(ctl.mean()) if len(ctl) else np.nan
    s["p"] = float((ctl >= s["per"]).mean()) if len(ctl) else np.nan
    return s


_BLOCK = None
def set_block(b):
    global _BLOCK; _BLOCK = b
def _block_of(mask):
    return _BLOCK if _BLOCK is not None else np.ones(len(mask), bool)
