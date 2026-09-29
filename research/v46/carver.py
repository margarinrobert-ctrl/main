"""Carver's breakout indicator, implemented to the published definition, and audited for causality.

THE DEFINITION (Rob Carver, *Systematic Trading* / *Advanced Futures Trading Strategies*):

    max_N   = rolling maximum of price over N
    min_N   = rolling minimum of price over N
    mean_N  = (max_N + min_N) / 2
    raw     = (price - mean_N) / (max_N - min_N)          in [-0.5, +0.5] by construction
    smooth  = EWMA(raw, span = N / 4)
    forecast= smooth * 40                                  scaled so |forecast| tops out near 20
    forecast= clip(forecast, -20, +20)

Carver's own span set is N in {10, 20, 40, 80, 160, 320}, and he notes the fastest variants are
eaten by costs on most instruments -- which is worth remembering before reading any 10-bar cell.

WHAT THIS IS NOT. Carver uses the forecast as a CONTINUOUS POSITION SIZE in a portfolio that nets
many instruments and many speeds. This branch trades one contract with barriers, so the forecast is
adapted here into an ENTRY TRIGGER and an optional forecast-based EXIT. That adaptation is mine,
not Carver's, and it is the thing being tested -- a result here is a statement about the adaptation,
never a verdict on his system as specified.

IT IS ALSO NOT A DONCHIAN BREAKOUT, which matters given how much of this branch is Donchian. The
Donchian trigger is BINARY and fires at a new extreme; this is a CONTINUOUS, RANGE-NORMALISED
position within the channel, smoothed. At +20 price sits at the top of its N-bar range; at 0 it
sits in the middle. The overlap is measured in `run_v46.py` rather than assumed.

Usage: imported by v46grid.py
"""
from __future__ import annotations

import numpy as np
from numba import njit

SPANS = (10, 20, 40, 80, 160, 320)          # Carver's own set
SMOOTH_DIV = (2, 4, 8)                      # 4 is his default
CAP = 20.0
SCALAR = 40.0


@njit(cache=True)
def _rollmaxmin(x, n):
    m = len(x)
    hi = np.full(m, np.nan); lo = np.full(m, np.nan)
    for i in range(n - 1, m):
        a = x[i - n + 1]; b = x[i - n + 1]
        for j in range(i - n + 2, i + 1):
            if x[j] > a:
                a = x[j]
            if x[j] < b:
                b = x[j]
        hi[i] = a; lo[i] = b
    return hi, lo


@njit(cache=True)
def _ewma(x, span):
    m = len(x)
    out = np.full(m, np.nan)
    alpha = 2.0 / (span + 1.0)
    started = False
    acc = 0.0
    for i in range(m):
        v = x[i]
        if np.isnan(v):
            continue
        if not started:
            acc = v; started = True
        else:
            acc = alpha * v + (1.0 - alpha) * acc
        out[i] = acc
    return out


def forecast(close, span, smooth_div=4):
    """Carver's breakout forecast. Reads bars up to and including the current close, nothing after."""
    c = np.asarray(close, float)
    hi, lo = _rollmaxmin(c, int(span))
    rng = hi - lo
    mean = (hi + lo) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.where(rng > 0, (c - mean) / rng, 0.0)
    raw = np.where(np.isfinite(rng), raw, np.nan)
    sm = _ewma(raw, max(1.0, span / float(smooth_div)))
    f = SCALAR * sm
    return np.clip(f, -CAP, CAP)


def audit(close, probes=(4000, 9000, 15000), tol=1e-9):
    """Truncation audit -- recompute on history ENDING at bar i and require the value to match.

    An EWMA seeded at the first non-NaN is causal by construction, and a rolling max/min is too;
    this proves it on the actual arrays rather than arguing it from the source, which is the only
    test that has ever caught a leak on this branch."""
    bad = {}
    for span in SPANS:
        for sd in SMOOTH_DIV:
            full = forecast(close, span, sd)
            for i in probes:
                if i >= len(close):
                    continue
                cut = forecast(close[:i + 1], span, sd)
                a, b = full[i], cut[i]
                if np.isnan(a) and np.isnan(b):
                    continue
                if not np.isfinite(a) or not np.isfinite(b) or abs(a - b) > tol * max(1.0, abs(a)):
                    bad.setdefault((span, sd), []).append(i)
    return bad
