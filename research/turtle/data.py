"""Bars and costs for both instruments, on one interface.

The two feeds are NOT interchangeable and are never pooled: NQ futures (this repo's 5-minute
file, whose price LEVELS are synthetic -- see `research/us100.py`) and US100 CFD 15-minute. They
carry different point values, different costs and different session conventions, so every result
is reported per instrument.

COSTS ARE IN INDEX POINTS per unit, and they are assumptions, not measurements -- OHLC bars carry
no spread. MNQ: $1.44 round turn at $2/point = 0.72 points. US100 CFD: a ~1.0 point quoted spread
= 1.0 point round turn. Slippage is charged per fill on top.
"""
from __future__ import annotations

import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COSTS = {"NQ": dict(cost_pts=0.72, slip_pts=0.25, point_value=2.0),
         "US100": dict(cost_pts=1.00, slip_pts=0.25, point_value=1.0)}


def bars(inst, tf):
    if inst == "NQ":
        from oner_union import bars as nqbars
        d = nqbars(tf)
        import pandas as pd
        d["idx"] = pd.DatetimeIndex(d["df"].index)
        return d
    if inst == "US100":
        from edgelab import data as ud
        return ud.bars(tf)
    raise ValueError(inst)


def blocks(inst, d):
    """Research / out-of-sample split, per instrument's established convention on this branch."""
    import pandas as pd
    ix = pd.DatetimeIndex(d["idx"])
    if inst == "NQ":
        from oner_union import _cut
        si, cut, _ = _cut(d)
        return dict(research=np.asarray(si < cut), oos=np.asarray(si >= cut))
    disc = np.asarray(ix < pd.Timestamp("2022-01-01"))
    val = np.asarray((ix >= pd.Timestamp("2022-01-01")) & (ix < pd.Timestamp("2024-01-01")))
    prod = np.asarray(ix >= pd.Timestamp("2024-01-01"))
    return dict(research=disc, validation=val, production=prod, oos=val | prod)


def split_trades(res, mask):
    """Attribute a trade to a block by its ENTRY bar."""
    bi = res["bar_in"]
    return np.asarray(mask)[bi] if len(bi) else np.zeros(0, bool)


def stats(res, sel=None, point_value=1.0):
    R = res["R"] if sel is None else res["R"][sel]
    P = res["pnl"] if sel is None else res["pnl"][sel]
    if len(R) == 0:
        return None
    wins, losses = R[R > 0], R[R <= 0]
    eq = np.cumsum(R)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    return dict(n=len(R), win=100.0 * float((R > 0).mean()), expR=float(R.mean()),
                totalR=float(R.sum()), pf=float(wins.sum() / -losses.sum())
                if len(losses) and losses.sum() < 0 else np.inf,
                maxdd_R=dd, dollars=float(P.sum() * point_value),
                avg_units=float((res["units"] if sel is None else res["units"][sel]).mean()))


def session_gate(d, start_min, end_min):
    """Entries allowed only inside [start, end) minutes-of-day, New York.

    EXITS ARE NOT GATED. A Turtle position is held for days, so forcing it flat at a session
    boundary would be a different strategy, not a filtered one. Only the decision to OPEN is
    restricted -- which is also the only thing a session filter can honestly claim to control.

    `start_min > end_min` wraps around midnight (e.g. 1080 -> 240 is 18:00 to 04:00).
    """
    import numpy as np
    mod = np.asarray(d["mod"], int)
    if start_min == end_min:
        return np.ones(len(mod), bool)
    if start_min < end_min:
        return (mod >= start_min) & (mod < end_min)
    return (mod >= start_min) | (mod < end_min)


def hhmm(minutes):
    return f"{int(minutes)//60:02d}:{int(minutes)%60:02d}"
