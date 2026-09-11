"""Chop / range detection, so a breakout is only taken when the market can actually trend.

WHY THIS IS THE RIGHT LEVER FOR A BREAKOUT SYSTEM. A channel breakout has one characteristic
failure mode: the false break in a range, where price pokes through the high and immediately
reverses. `scalp/discover.py` measured every breakout family as having NEGATIVE excess over a
day-clustered control intraday, and a range-bound tape is the obvious suspect. This module
supplies the measures that separate a trending market from a chopping one, all CAUSAL (trailing
windows only), so the breakout can be gated on regime rather than abandoned.

EVERY MEASURE IS ORIENTED THE SAME WAY: higher = more trending, lower = more chop. Where the
textbook definition runs the other way -- the Choppiness Index rises with chop -- it is negated
here and the name says so, because a gate whose direction is ambiguous is a gate that eventually
gets used backwards.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _roll(x, n, fn):
    return getattr(pd.Series(x).rolling(n, min_periods=n), fn)().to_numpy()


def efficiency_ratio(c, n=20):
    """Kaufman: |net move| / sum|bar moves|. 1.0 = a straight line, 0 = pure noise."""
    net = np.abs(c - np.roll(c, n))
    vol = _roll(np.abs(np.r_[0.0, np.diff(c)]), n, "sum")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = net / vol
    out[:n] = np.nan
    return out


def choppiness(h, l, c, n=14):
    """NEGATED Choppiness Index, so higher = more trending (the raw index rises with chop)."""
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    s = _roll(tr, n, "sum")
    rng = _roll(h, n, "max") - _roll(l, n, "min")
    with np.errstate(divide="ignore", invalid="ignore"):
        chop = 100.0 * np.log10(s / rng) / np.log10(n)
    return -chop


def vhf(c, n=28):
    """Vertical Horizontal Filter: range over summed absolute change. Higher = trending."""
    hi = _roll(c, n, "max"); lo = _roll(c, n, "min")
    denom = _roll(np.abs(np.r_[0.0, np.diff(c)]), n, "sum")
    with np.errstate(divide="ignore", invalid="ignore"):
        return (hi - lo) / denom


def ema_cross_count(c, fast_n=9, slow_n=21, n=40):
    """Crosses of fast over slow in the last n bars. NEGATED: fewer crosses = trending."""
    f = pd.Series(c).ewm(span=fast_n, adjust=False).mean().to_numpy()
    s = pd.Series(c).ewm(span=slow_n, adjust=False).mean().to_numpy()
    above = (f > s).astype(float)
    flips = np.abs(np.r_[0.0, np.diff(above)])
    return -_roll(flips, n, "sum")


def range_expansion(h, l, n=20):
    """Current n-bar range against its own trailing median. Higher = expanding out of a range."""
    rng = _roll(h, n, "max") - _roll(l, n, "min")
    med = _roll(rng, 5 * n, "median")
    with np.errstate(divide="ignore", invalid="ignore"):
        return rng / med


def atr_expansion(h, l, c, fast_n=5, slow_n=50):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f = pd.Series(tr).ewm(span=fast_n, adjust=False).mean().to_numpy()
    s = pd.Series(tr).ewm(span=slow_n, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return f / s


def directional_strength(h, l, c, n=14):
    """ADX with the DI sign attached: positive = strong UP trend, negative = strong DOWN."""
    up = np.maximum(h - np.roll(h, 1), 0.0); dn = np.maximum(np.roll(l, 1) - l, 0.0)
    up[0] = dn[0] = 0.0
    pdm = np.where(up > dn, up, 0.0); ndm = np.where(dn > up, dn, 0.0)
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    rma = lambda x: pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    atr = rma(tr)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * rma(pdm) / atr
        ndi = 100.0 * rma(ndm) / atr
        dx = 100.0 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9)
    adx = rma(dx)
    return adx * np.sign(pdi - ndi), adx, pdi - ndi


def r_squared(c, n=20):
    """R^2 of a straight-line fit to the last n closes. 1 = clean trend, 0 = chop."""
    x = np.arange(n, dtype=float)
    xm = x.mean(); sxx = float(((x - xm) ** 2).sum())

    def f(w):
        ym = w.mean()
        sxy = float(((x - xm) * (w - ym)).sum())
        syy = float(((w - ym) ** 2).sum())
        return (sxy * sxy) / (sxx * syy) if syy > 0 else np.nan

    return pd.Series(c).rolling(n, min_periods=n).apply(f, raw=True).to_numpy()


def build(d, with_r2=True):
    """All trend-quality measures, oriented so HIGHER = MORE TRENDING."""
    h, l, c = d["h"], d["l"], d["c"]
    _dstr, adx, di = directional_strength(h, l, c)
    out = {
        "eff_ratio_10": efficiency_ratio(c, 10),
        "eff_ratio_20": efficiency_ratio(c, 20),
        "eff_ratio_50": efficiency_ratio(c, 50),
        "neg_choppiness_14": choppiness(h, l, c, 14),
        "neg_choppiness_28": choppiness(h, l, c, 28),
        "vhf_28": vhf(c, 28),
        "neg_ema_crosses_40": ema_cross_count(c, 9, 21, 40),
        "range_expansion_20": range_expansion(h, l, 20),
        "atr_expansion_5_50": atr_expansion(h, l, c),
        "adx": adx,
        "di_spread": di,
    }
    if with_r2:
        out["r2_trend_20"] = r_squared(c, 20)
    return out
