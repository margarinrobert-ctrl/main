"""NQ context for the V9 scalping work. Research/locked split is the branch's standard 65%."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
sys.path.insert(0,"research/turtle15"); sys.path.insert(0,"research/v8opt")
import fastbars, mirror, feats  # noqa: E402

def load(tf=15, e1=30, e2=55, x=20):
    d = fastbars.bars(tf)
    atr  = mirror.wilder_atr(d["h"], d["l"], d["c"], 20)
    atr5 = mirror.wilder_atr(d["h"], d["l"], d["c"], 5)
    C    = mirror.channels(d["h"], d["l"], e1, e2, x, x)
    F    = feats.build(d, atr, mirror.channels(d["h"], d["l"]))
    cost = 1.72 if tf >= 15 else 1.72          # MNQ round turn in points, per research/costs.py
    sess = np.asarray(d["sess"]); us = np.unique(sess)
    cut  = us[int(0.65 * len(us))]
    res  = sess < cut                          # SELECT ON RESEARCH, read the locked block once
    return dict(d=d, atr=atr, atr5=atr5, C=C, F=F, cost=cost, mod=np.asarray(d["mod"]),
                res=res, lock=~res, ts=pd.to_datetime(d["ts"]))

def sharpe(t, d, per_day=True):
    """Daily-aggregated Sharpe, annualised on 252 -- a per-TRADE Sharpe flatters high trade counts."""
    if len(t) < 5: return np.nan
    day = pd.Series(np.asarray(d["sess"])[t.ent.to_numpy()])
    g = t.assign(day=day.values).groupby("day").pnl.sum()
    if g.std(ddof=1) == 0 or len(g) < 5: return np.nan
    return float(g.mean() / g.std(ddof=1) * np.sqrt(252))
