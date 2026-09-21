"""Bars, sessions and the locked split for the US30 30-second file.

WHY 30-SECOND SOURCE DATA MATTERS HERE. Every study on this branch has had to book a bar that
contains BOTH the stop and the target as a loss, because the intrabar path is unknown
(RESEARCH_PROTOCOL.md stage 0). This file is 30-second, so for any bar size at or above one
minute the path INSIDE the signal bar is observed and the ambiguity is resolved rather than
assumed. `sim.py` walks the 30s array, not the aggregated one.

THE SPLIT IS THE FIRST 65% OF SESSIONS, taken from the session list itself so no caller can
invent its own (CLAUDE.md). It is computed on the sessions a given range window can actually
produce, so shortening the window cannot silently move the boundary.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

SRC = "/root/.claude/uploads/43c8e2d5-a387-5930-9ae9-7c96f7e6b53d/8f6e7d65-US30_30s.csv"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

# US30 accounting. The round turn is the figure this branch already uses for this instrument
# (2.29 points, the NINE_AM Pine header); the point value is the $1/point CFD contract the file's
# 0.01 price grid implies. Costs are applied at READ time in sim.py, never baked into the cached
# gross number, so a cost-sensitivity sweep is free.
PV = 1.0            # dollars per index point
RT_PTS = 2.29       # round-turn cost in points: spread + slippage + commission
STOP_SLIP = 0.50    # extra points paid when a stop is the exit

STOP, TARGET, FLAT, MAXHOLD, NOFILL = 1, 2, 3, 4, 5


def _load30() -> pd.DataFrame:
    os.makedirs(CACHE, exist_ok=True)
    pq = os.path.join(CACHE, "us30_30s.parquet")
    if os.path.exists(pq):
        return pd.read_parquet(pq)
    d = pd.read_csv(SRC, parse_dates=["ny"])
    d = d.sort_values("ny").reset_index(drop=True)
    d["mod"] = d.ny.dt.hour * 60 + d.ny.dt.minute
    d["date"] = d.ny.dt.normalize()
    d.to_parquet(pq)
    return d


def bars(tf: int) -> dict:
    """N-minute bars plus the index range of the 30s bars each one spans.

    `s0`/`s1` are the half-open slice of the 30s array covered by aggregated bar i, which is what
    lets the exit walk see inside the bar it entered on.
    """
    d = _load30()
    # floor each 30s stamp to its tf-minute bucket, within the calendar day
    key = d["date"].values.astype("datetime64[D]").astype(np.int64) * 10000 + (d["mod"].values // tf)
    chg = np.empty(len(key), bool); chg[0] = True; chg[1:] = key[1:] != key[:-1]
    gid = np.cumsum(chg) - 1
    n = gid[-1] + 1
    s0 = np.zeros(n, np.int64); s1 = np.zeros(n, np.int64)
    idx = np.flatnonzero(chg)
    s0[:] = idx
    s1[:-1] = idx[1:]; s1[-1] = len(key)

    o = d.open.values[s0]
    c = d.close.values[s1 - 1]
    hi = np.maximum.reduceat(d.high.values, s0)
    lo = np.minimum.reduceat(d.low.values, s0)
    vol = np.add.reduceat(d.volume.values, s0)
    mod = d["mod"].values[s0]
    day = d["date"].values[s0]

    # session index: a plain calendar-date index. The rule never holds overnight (it flattens at
    # 16:00), so a futures 18:00 roll would change nothing and a calendar date is the readable one.
    udays, si = np.unique(day, return_inverse=True)
    return dict(tf=tf, o=o, h=hi, l=lo, c=c, v=vol, mod=mod.astype(np.int64),
                si=si.astype(np.int64), days=udays, n=len(o),
                s0=s0, s1=s1,
                t30o=d.open.values, t30h=d.high.values, t30l=d.low.values,
                t30c=d.close.values, t30mod=d["mod"].values.astype(np.int64),
                t30si=si[gid].astype(np.int64))


def split(b: dict, sessions: np.ndarray | None = None, frac: float = 0.65):
    """Session index at which the locked block starts.

    `sessions` is the set of session indices the rule can actually trade; the boundary is the
    65th percentile OF THOSE, so a window that only exists on part of the file still splits its
    own sample 65/35 rather than inheriting a boundary from sessions it can never trade.
    """
    if sessions is None or len(sessions) == 0:
        u = np.arange(len(b["days"]))
    else:
        u = np.unique(sessions)
    k = int(np.floor(frac * len(u)))
    return int(u[min(k, len(u) - 1)]), len(u)


def atr(b: dict, n: int = 14) -> np.ndarray:
    """ta.ema(ta.tr(true), n) -- a SPAN, which is what the Pine uses, not Wilder's ta.atr."""
    h, l, c = b["h"], b["l"], b["c"]
    pc = np.empty_like(c); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = 2.0 / (n + 1.0)
    out = np.empty_like(tr); out[0] = tr[0]
    for i in range(1, len(tr)):
        out[i] = a * tr[i] + (1 - a) * out[i - 1]
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2.0 / (n + 1.0)
    out = np.empty_like(x, dtype=float); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out
