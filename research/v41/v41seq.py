"""V41 -- EMA 13/48 cross as the FIRST signal, Donchian as CONFIRMATION.

THE STRUCTURE THE BRIEF ASKS FOR is a SEQUENCE, not a conjunction: the EMA cross fires, and then a
Donchian breakout within some window confirms it. That is a different rule from "EMA state AND
breakout", and the difference is testable, so both are in the grid as an explicit axis:

    mode "cross"   entry on a breakout occurring within `win` bars AFTER an upward EMA cross
    mode "state"   entry on a breakout while the fast EMA is simply above the slow one

TWO AXES IN THIS GRID ARE PARTLY INERT, AND THAT MATTERS FOR THE MULTIPLICITY COUNT
(`CLAUDE.md`: an inert axis must be excluded from the effective grid size, or the correction is
computed against a test count that was never really run):

  * under mode "state" the `win` axis does nothing at all -- there is no recency requirement to
    widen -- so those five cells are ONE cell.
  * under mode "cross" with `win = 0` (no recency requirement) the EMA condition degenerates to
    "a cross has happened at some point", which is true almost everywhere. THAT IS DELIBERATE:
    it is the grid's own built-in ablation, the Donchian-alone control, and it is labelled as
    such rather than being quietly counted as a strategy.

Nominal cells 103,680; EFFECTIVE distinct configurations 62,208. Both are printed.

THE TURTLE SCRIPT THE BRIEF STARTS FROM used ta.atr (Wilder's RMA) deliberately, because the
Turtle definition and the Python engine it was validated against both do. This module keeps that:
`atr_mode="wilder"` is the default here, unlike the rest of the branch which uses ema(TR, n).

Usage: imported by run_v41.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
import indicators as I       # noqa: E402
import v38grid as G          # noqa: E402

TFS = (15, 30, 60)
EMA_F = (8, 13, 21)                 # the brief's 13, with a rung either side
EMA_S = (34, 48, 62)                # the brief's 48, with a rung either side
EMA_MODE = ("cross", "state")
WIN = (0, 5, 10, 20, 40)            # bars the confirmation may lag the cross; 0 = no requirement
DON_E = (10, 20, 30, 55)
DON_X = (10, 20)
STOP = (1.5, 2.0, 2.5, 3.0)
TP = (0.0, 2.0, 3.0)                # 0 = no take profit
GATE = ("off", "adx<22", "adx>=20", "chop<=45")

N_NOMINAL = (len(TFS) * len(EMA_F) * len(EMA_S) * len(EMA_MODE) * len(WIN) * len(DON_E)
             * len(DON_X) * len(STOP) * len(TP) * len(GATE))
# state mode collapses the five window rungs to one
N_EFFECTIVE = N_NOMINAL // 2 + N_NOMINAL // 2 // len(WIN)


def chop(h, l, c, n=14):
    tr = I.true_range(h, l, c)
    return (100 * np.log10(I.rsum(tr, n) / np.maximum(I.rmax(h, n) - I.rmin(l, n), 1e-9))
            / np.log10(n))


@njit(cache=True)
def _since(flag):
    """Bars since `flag` was last true, -1 before it ever is. One pass, no lookahead."""
    n = len(flag)
    out = np.full(n, -1, np.int64)
    last = -1
    for i in range(n):
        if flag[i]:
            last = i
        out[i] = -1 if last < 0 else i - last
    return out


def prep(tf, atr_len=20):
    """Bars plus every series the grid can ask for. ATR is WILDER's, matching the source script."""
    import fastbars as FB
    d = FB.bars(tf)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr = I.rma(I.true_range(h, l, c), atr_len)        # Wilder, as the Turtle spec and the script
    P = dict(o=o, h=h, l=l, c=c, v=d["v"], mod=d["mod"], atr=atr, n=len(c), pv=G.PV,
             day=pd.to_datetime(d["ts"]).normalize().astype("int64").to_numpy())
    adx, pdi, mdi = I.adx_di(h, l, c, 14)
    P["gate"] = {"off": np.ones(len(c), bool), "adx<22": adx < 22.0, "adx>=20": adx >= 20.0,
                 "chop<=45": chop(h, l, c, 14) <= 45.0}
    P["ema"] = {}
    for a in EMA_F:
        P["ema"][a] = I.ema(c, a)
    for b in EMA_S:
        P["ema"][b] = I.ema(c, b)
    P["brk"] = {e: c > I.shift(I.rmax(h, e), 1) for e in DON_E}
    P["since"] = {}
    for a in EMA_F:
        for b in EMA_S:
            if a >= b:
                continue
            up = P["ema"][a] > P["ema"][b]
            cross = np.zeros(len(c), bool)
            cross[1:] = up[1:] & ~up[:-1]
            P["since"][(a, b)] = (_since(cross), up)
    return P


def signal(P, a, b, mode, win, e, gate):
    """The sequenced entry: an EMA cross, then a Donchian breakout confirming it within `win`."""
    since, up = P["since"][(a, b)]
    if mode == "state":
        ema_ok = up
    elif win <= 0:
        ema_ok = since >= 0                    # the DONCHIAN-ALONE control, labelled as such
    else:
        ema_ok = (since >= 0) & (since <= win)
    m = P["brk"][e] & ema_ok & P["gate"][gate] & np.isfinite(P["atr"]) & (P["atr"] > 0)
    return np.flatnonzero(m).astype(np.int64)


def configs():
    """Every cell, with its own inert-axis flag attached so nothing is double-counted later."""
    from itertools import product
    for tf, a, b, mode, win, e, x, sn, tp, g in product(
            TFS, EMA_F, EMA_S, EMA_MODE, WIN, DON_E, DON_X, STOP, TP, GATE):
        if a >= b:
            continue
        inert = (mode == "state" and win != WIN[0])     # duplicate of the win=0 state cell
        yield dict(tf=tf, ema_f=a, ema_s=b, mode=mode, win=win, don_e=e, don_x=x,
                   stop=sn, tp=tp, gate=g, inert=inert,
                   is_control=(mode == "cross" and win == 0))
