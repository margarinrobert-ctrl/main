"""US30 Donchian + EMA200 with a FIXED 50-point stop and 50 / 100 / 150-point targets.

THE FIRST THING THAT HAS TO BE MEASURED IS NOT A MODEL. A fixed POINT barrier is not scale-free,
and US30 went from ~16,000 in 2016 to ~45,000 in 2025 -- so "50 points" is a 2.8x smaller trade at
the end of the sample than at the start, both as a fraction of price and (unless ATR moved exactly
with price) as a fraction of the day's range. Every hit rate below is therefore a mixture of two
different strategies unless that drift is small, and `geometry()` reports it before anything else.

THE SECOND THING IS THE BREAK-EVEN. With cost c expressed in units of the stop, a target at R times
the stop needs a win rate of (1 + c) / (1 + R) to break even against a driftless price. On US30 the
round turn is 2.29 points = 4.58% of a 50-point stop, so:

    target      R      driftless bound      break-even after cost      gap
    50 pt      1.0           50.00%                 52.29%           +2.29
    100 pt     2.0           33.33%                 34.86%           +1.53
    150 pt     3.0           25.00%                 26.15%           +1.15

That cost gap is SMALL -- unusually so for this branch, where a 0.75xATR scalping stop carries 24%
of risk. A 50-point stop on US30 is not a cost problem. Whatever fails here fails on direction.

The event stream: a Donchian entry-channel break, taken only in the direction the EMA200 state
allows, filled at the next open, with a fixed 50-point stop, a fixed target, and a declared hold
cap. Scored in POINTS (the barriers are in points, so R and points differ only by a constant) and
in percent of entry price, which is the unit that survives the level drift.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
from v38 import v38feeds as F  # noqa: E402

COST = 2.29
STOP_PTS = 50.0
TARGETS = (50.0, 100.0, 150.0)


def load(tf=15):
    f = F.load("US30L")[["open", "high", "low", "close"]]
    if tf != 15:
        f = f.resample(f"{tf}min", label="left", closed="left").agg(
            dict(open="first", high="max", low="min", close="last")).dropna()
    f = f.copy()
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f["atr"] = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    f["mod"] = f.index.hour * 60 + f.index.minute
    return f


def breakeven(target_pts, stop_pts=STOP_PTS, cost=COST):
    r = target_pts / stop_pts
    c = cost / stop_pts
    return 1.0 / (1.0 + r), (1.0 + c) / (1.0 + r)


def geometry(f):
    """Is 50 points the same trade in 2016 and 2025? Reported before any hit rate."""
    g = pd.DataFrame(index=f.index)
    g["pct_of_price"] = 100.0 * STOP_PTS / f["close"].to_numpy()
    g["in_atr"] = STOP_PTS / f["atr"].to_numpy()
    g["year"] = f.index.year
    return g.groupby("year")[["pct_of_price", "in_atr"]].median()


@njit(cache=True)
def walk(o, h, l, c, ehi, elo, ok_up, ok_dn, stop_pts, tgt_pts, hold, cost, m0, m1, mod):
    """One position at a time. A bar that touches both barriers is resolved as the STOP, and the
    ambiguous share is returned so the reader can see how much of the answer that convention is."""
    n = len(c)
    eb = np.full(n, -1, np.int64); out = np.empty(n)
    sd = np.empty(n, np.int64); hl = np.empty(n, np.int64)
    why = np.empty(n, np.int64); amb = np.empty(n, np.int64)
    cnt = 0; last = -1
    for i in range(1, n - 1):
        if i <= last:
            continue
        if m0 >= 0 and (mod[i] < m0 or mod[i] >= m1):
            continue
        if np.isnan(ehi[i]) or np.isnan(elo[i]):
            continue
        s = 0
        if c[i] > ehi[i] and ok_up[i] == 1:
            s = 1
        elif c[i] < elo[i] and ok_dn[i] == 1:
            s = -1
        if s == 0:
            continue
        j = i + 1
        ent = o[j]
        stop = ent - s * stop_pts
        targ = ent + s * tgt_pts
        x = -1; px = 0.0; w = 2; a = 0
        for t in range(j, n):
            hit_s = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            hit_t = (h[t] >= targ) if s > 0 else (l[t] <= targ)
            if hit_s and hit_t:
                a = 1
            if hit_s:
                x = t; px = stop; w = 0
                break
            if hit_t:
                x = t; px = targ; w = 1
                break
            if hold > 0 and t - j >= hold:
                x = t; px = c[t]; w = 2
                break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 2
        eb[cnt] = j
        out[cnt] = s * (px - ent) - cost
        sd[cnt] = s; hl[cnt] = x - j; why[cnt] = w; amb[cnt] = a
        cnt += 1
        last = x
    return eb[:cnt], out[:cnt], sd[:cnt], hl[:cnt], why[:cnt], amb[:cnt]


@njit(cache=True)
def walk_at(o, h, l, c, sig, side, stop_pts, tgt_pts, hold, cost):
    n = len(c); m = len(sig)
    out = np.full(m, np.nan)
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        s = side[q]; j = i + 1
        ent = o[j]
        stop = ent - s * stop_pts
        targ = ent + s * tgt_pts
        x = -1; px = 0.0
        for t in range(j, n):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if (h[t] >= targ) if s > 0 else (l[t] <= targ):
                x = t; px = targ
                break
            if hold > 0 and t - j >= hold:
                x = t; px = c[t]
                break
        if x < 0:
            x = n - 1; px = c[n - 1]
        out[q] = s * (px - ent) - cost
        last = x
    return out


def chan(h, l, n):
    return (pd.Series(h).rolling(n).max().shift(1).to_numpy(),
            pd.Series(l).rolling(n).min().shift(1).to_numpy())


def signals(f, ent_ch=20, ema_len=200):
    c = f["close"].to_numpy()
    eh, el = chan(f["high"].to_numpy(), f["low"].to_numpy(), ent_ch)
    e = pd.Series(c).ewm(span=ema_len, adjust=False).mean().to_numpy()
    return eh, el, (c > e).astype(np.int64), (c < e).astype(np.int64), e


def pf(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan
