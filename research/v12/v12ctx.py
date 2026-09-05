"""Multi-market context for the Donchian 30/20 intraday trend programme.

THE CHANNEL IS FIXED BY THE BRIEF: entry 30, exit 20. Nothing in this module searches it. What is
searched is the TREND and REGIME conditions around it, the stop, and the intraday window -- on the
TRAIN block of US30 only.

A COST IS A FRACTION OF RISK, NOT A NUMBER OF POINTS. 1.72 points is 3.7% of NQ's 2N stop, 2.8% of
US30's and 54.2% of GOLD's; charging one instrument's points in another's is how a gold study once
reported PF 0.35 as a decisive failure where the honest figure was 0.94. Every market here is
charged the same FRACTION that MNQ pays.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
sys.path.insert(0,"research/turtle15"); sys.path.insert(0,"research/v8opt")
import mirror, feats, fastbars, markets  # noqa: E402

JUDGE = pd.Timestamp("2026-01-01")     # US30/US100 2026: later than every study on this branch
DON_E, DON_X = 30, 20                  # FIXED BY THE BRIEF

_NQ_FRACTION = None
def _cost_fraction():
    global _NQ_FRACTION
    if _NQ_FRACTION is None:
        b = fastbars.bars(15)
        a = mirror.wilder_atr(b["h"], b["l"], b["c"], 20)
        _NQ_FRACTION = 1.72 / (2 * float(np.nanmedian(a)))
    return _NQ_FRACTION

def load(path, split=JUDGE):
    d, si, cut = markets.load_iso(path)
    ts = pd.to_datetime(d["ts"])
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], 20)
    C   = mirror.channels(d["h"], d["l"], DON_E, 55, DON_X, DON_X)
    F   = feats.build(d, atr, mirror.channels(d["h"], d["l"]))
    cost = _cost_fraction() * 2 * float(np.nanmedian(atr))
    mod  = np.asarray(d["mod"])
    K = dict(d=d, ts=ts, atr=atr, C=C, F=F, cost=cost, mod=mod, N=float(np.nanmedian(atr)))
    if split is not None:
        K["train"] = np.asarray(ts < split); K["oos"] = np.asarray(ts >= split)
    else:                                    # XAU: no 2026 split, use the branch's 65% convention
        sess = np.asarray(d["sess"]); us = np.unique(sess); c2 = us[int(0.65*len(us))]
        K["train"] = sess < c2; K["oos"] = sess >= c2
    return K

def win(mod, lo, hi):
    """Entries inside [lo,hi); the last bar is excluded because entry is at the NEXT bar's open."""
    return (mod >= lo) & (mod < hi - 15)

def sharpe(t, d):
    """DAILY-aggregated Sharpe. A per-trade Sharpe flatters whatever trades most."""
    if len(t) < 8: return np.nan
    g = pd.Series(t.pnl.to_numpy()).groupby(np.asarray(d["sess"])[t.ent.to_numpy()]).sum()
    if len(g) < 8 or g.std(ddof=1) == 0: return np.nan
    return float(g.mean()/g.std(ddof=1)*np.sqrt(252))
