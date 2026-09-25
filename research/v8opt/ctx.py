"""Shared context: one place that decides the blocks, so no stage can quietly re-split them."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
sys.path.insert(0,"research/turtle15"); sys.path.insert(0,"research/v8opt")
import markets, mirror, feats, fastbars  # noqa: E402

JUDGE_FROM = pd.Timestamp("2026-01-01")     # US30 2026 was never searched by anything on this branch
WIN_LO, WIN_HI = 420, 600                   # 07:00-10:00 New York, the user's hard constraint
SUBWIN = [(420,450),(450,480),(480,510),(510,540),(540,570),(570,600)]

def load(path="data/US30_ISO_15m.csv"):
    d, si, cut = markets.load_iso(path)
    ts = pd.to_datetime(d["ts"])
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], 20)
    C   = mirror.channels(d["h"], d["l"], 30, 55, 20, 20)      # Version #8: e30/x20, e2=55/x2=20
    F   = feats.build(d, atr, mirror.channels(d["h"], d["l"]))
    a0  = mirror.wilder_atr(*[fastbars.bars(15)[k] for k in ("h","l","c")], 20)
    cost = (1.72 / (2*np.nanmedian(a0))) * 2*np.nanmedian(atr)  # a cost is a FRACTION of risk
    gate = np.nan_to_num(F["adx"] >= 15.0, nan=False)           # Version #8's only gate
    mod  = np.asarray(d["mod"])
    return dict(d=d, ts=ts, atr=atr, C=C, F=F, cost=cost, gate=gate, mod=mod,
                train=np.asarray(ts < JUDGE_FROM), oos=np.asarray(ts >= JUDGE_FROM))

def win(mod, lo, hi, flat=True):
    """Entries inside [lo,hi); the last bar is excluded because entry is at the NEXT bar's open."""
    return (mod >= lo) & (mod < hi - 15)
