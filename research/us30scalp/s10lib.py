"""Shared machinery for the S10 validation battery on the section-12 rule.

The rule under test is DERIVED, not fitted: Donchian 20 long + an ADX CEILING and/or the EMA
alignment, no ATR condition, 07:00-11:00 New York, flat at the 11:00 open, 50-point stop /
150-point target. Because nothing was fitted, the walk-forward that matters is the one with the
constants FIXED; a re-selecting arm is run beside it as the comparison, not as the headline.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

Z80 = 2.802
KW = dict(stop_a=50.0, tgt_a=150.0, hold=0, flat=S.FLAT, use_pts=1)


@njit(cache=True)
def _rma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    s = 0.0
    for i in range(n):
        s += x[i]
    out[n - 1] = s / n
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def adx_wilder(h, l, c, n=14):
    up, dn = h[1:] - h[:-1], l[:-1] - l[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr, pv, nv = _rma(tr, n), _rma(pdm, n), _rma(ndm, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi, ndi = 100 * pv / atr, 100 * nv / atr
        dx = 100 * np.abs(pdi - ndi) / (pdi + ndi)
    return np.r_[np.nan, _rma(np.nan_to_num(dx, nan=0.0), n)]


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def build_masks(h, l, c):
    a = adx_wilder(h, l, c)
    e13, e34, e89 = ema(c, 13), ema(c, 34), ema(c, 89)
    return {"adx<=20": np.nan_to_num(a, nan=999) <= 20,
            "adx>=25": np.nan_to_num(a, nan=0) >= 25,
            "ema align": (e13 > e34) & (e34 > e89)}


ARMS = [("base", []), ("+adx<=20", ["adx<=20"]), ("+ema align", ["ema align"]),
        ("+both", ["adx<=20", "ema align"]), ("conventional", ["ema align", "adx>=25"])]


def signals(f, conds, bm=None, M=None):
    s2, d2 = S.donchian(f, 20, 1)
    if M is None:
        M = build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    keep = np.ones(len(s2), bool)
    if bm is not None:
        keep &= np.isin(s2, np.flatnonzero(bm))
    for c in conds:
        keep &= M[c][s2]
    return s2[keep], d2[keep]


def trades(f, conds, bm=None, M=None, **over):
    sig, sd = signals(f, conds, bm, M)
    if len(sig) < 5:
        return pd.DataFrame()
    kw = dict(KW); kw.update(over)
    return S.walk(f, sig, sd, **kw)


def stats(t, nsess):
    if not len(t):
        return dict(n=0)
    p = t["pts"].to_numpy()
    se = p.std(ddof=1) / np.sqrt(len(p))
    d = t.groupby(t.ts.dt.normalize())["pts"].sum()
    dd = np.zeros(max(nsess, len(d))); dd[:len(d)] = d.to_numpy()
    eq = np.cumsum(p)
    mdd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(n=len(p), pts=float(p.mean()), sd=float(p.std(ddof=1)), t=float(p.mean() / se),
                mde=Z80 * se, pf=S.pf(p), win=float((p > 0).mean()), total=float(p.sum()),
                dd=mdd, ret_dd=float(p.sum() / mdd) if mdd > 0 else np.nan,
                sharpe=float(dd.mean() / dd.std(ddof=1) * np.sqrt(252)) if dd.std() > 0 else np.nan)


def daily(t, index):
    """Zero-filled daily P&L on a common session index."""
    if not len(t):
        return pd.Series(0.0, index=index)
    d = t.groupby(t.ts.dt.normalize())["pts"].sum()
    return d.reindex(index).fillna(0.0)
