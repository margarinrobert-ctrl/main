"""Trend indicators the shared library does not have, written to their published definitions.

`indicators.py` covers EMA/SMA/RSI/Stoch/MACD/ADX/Bollinger/Keltner. This adds the rest of the
trend-following toolbox so the pullback search can use it: Supertrend, Ichimoku, Parabolic SAR,
Hull, KAMA, DEMA, TEMA, Vortex, Aroon and Heikin-Ashi.

All causal: value at bar i uses bars up to and including i. The two recursive ones (PSAR, KAMA)
are written as explicit forward loops for exactly that reason -- a vectorised shortcut for either
is easy to write and easy to make peek.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
import indicators as I


def dema(x, n):
    e = I.ema(x, n)
    return 2 * e - I.ema(e, n)


def tema(x, n):
    e1 = I.ema(x, n); e2 = I.ema(e1, n); e3 = I.ema(e2, n)
    return 3 * e1 - 3 * e2 + e3


def hull(x, n):
    h = int(max(1, n // 2))
    s = int(max(1, round(np.sqrt(n))))
    return I.ema(2 * I.ema(x, h) - I.ema(x, n), s)


@njit(cache=True)
def _kama(x, n, fast, slow):
    out = np.empty(len(x)); out[:] = np.nan
    if len(x) <= n:
        return out
    out[n] = x[n]
    fsc = 2.0 / (fast + 1.0); ssc = 2.0 / (slow + 1.0)
    for i in range(n + 1, len(x)):
        change = abs(x[i] - x[i - n])
        vol = 0.0
        for k in range(i - n + 1, i + 1):
            vol += abs(x[k] - x[k - 1])
        er = change / vol if vol > 0 else 0.0
        sc = (er * (fsc - ssc) + ssc) ** 2
        out[i] = out[i - 1] + sc * (x[i] - out[i - 1])
    return out


def kama(x, n=10, fast=2, slow=30):
    return _kama(np.asarray(x, np.float64), n, float(fast), float(slow))


@njit(cache=True)
def _psar(h, l, step, mx):
    n = len(h)
    out = np.empty(n); out[:] = np.nan
    if n < 3:
        return out
    up = True
    sar = l[0]; ep = h[0]; af = step
    out[0] = sar
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            if i >= 2:
                sar = min(sar, l[i - 1], l[i - 2])
            if l[i] < sar:
                up = False; sar = ep; ep = l[i]; af = step
            elif h[i] > ep:
                ep = h[i]; af = min(af + step, mx)
        else:
            if i >= 2:
                sar = max(sar, h[i - 1], h[i - 2])
            if h[i] > sar:
                up = True; sar = ep; ep = h[i]; af = step
            elif l[i] < ep:
                ep = l[i]; af = min(af + step, mx)
        out[i] = sar
    return out


def psar(h, l, step=0.02, mx=0.2):
    return _psar(np.asarray(h, np.float64), np.asarray(l, np.float64), step, mx)


def supertrend(h, l, c, n=10, mult=3.0):
    """Returns (line, direction) with direction +1 up, -1 down."""
    atr_ = I.ema(I.true_range(h, l, c), n)
    hl2 = (h + l) / 2.0
    ub = hl2 + mult * atr_
    lb = hl2 - mult * atr_
    N = len(c)
    fub = np.copy(ub); flb = np.copy(lb)
    for i in range(1, N):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
    d = np.ones(N, np.int64)
    line = np.copy(flb)
    for i in range(1, N):
        if d[i - 1] == 1 and c[i] < flb[i]:
            d[i] = -1
        elif d[i - 1] == -1 and c[i] > fub[i]:
            d[i] = 1
        else:
            d[i] = d[i - 1]
        line[i] = flb[i] if d[i] == 1 else fub[i]
    return line, d


def ichimoku(h, l, c, a=9, b=26, s=52):
    """Tenkan, Kijun and the two cloud lines, shifted forward by `b` as the definition requires."""
    conv = (I.rmax(h, a) + I.rmin(l, a)) / 2.0
    base = (I.rmax(h, b) + I.rmin(l, b)) / 2.0
    span_a = I.shift((conv + base) / 2.0, b)
    span_b = I.shift((I.rmax(h, s) + I.rmin(l, s)) / 2.0, b)
    return conv, base, span_a, span_b


def vortex(h, l, c, n=14):
    tr = I.true_range(h, l, c)
    vp = np.abs(h - I.shift(l))
    vm = np.abs(l - I.shift(h))
    s = np.maximum(I.rsum(tr, n), 1e-12)
    return I.rsum(vp, n) / s, I.rsum(vm, n) / s


def aroon(h, l, n=25):
    up = np.full(len(h), np.nan); dn = np.full(len(h), np.nan)
    for i in range(n, len(h)):
        w_h = h[i - n:i + 1]; w_l = l[i - n:i + 1]
        up[i] = 100.0 * (n - (n - int(np.argmax(w_h)))) / n
        dn[i] = 100.0 * (n - (n - int(np.argmin(w_l)))) / n
    return up, dn


def heikin(o, h, l, c):
    ha_c = (o + h + l + c) / 4.0
    ha_o = np.empty(len(c)); ha_o[0] = (o[0] + c[0]) / 2.0
    for i in range(1, len(c)):
        ha_o[i] = (ha_o[i - 1] + ha_c[i - 1]) / 2.0
    return ha_o, ha_c


EMA_SET = (5, 8, 9, 10, 12, 20, 21, 26, 34, 50, 55, 89, 100, 144, 200)
EMA_PAIRS = ((5, 20), (8, 21), (9, 21), (10, 20), (12, 26), (20, 50), (21, 55),
             (34, 89), (50, 100), (50, 200), (55, 200), (89, 200), (100, 200))


if __name__ == "__main__":
    from bos_choch import prep
    d = prep(30)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    line, dr = supertrend(h, l, c)
    conv, base, sa, sb = ichimoku(h, l, c)
    vp, vm = vortex(h, l, c)
    au, ad = aroon(h, l)
    print(f"trend indicators on {len(c):,} 30m bars")
    for nm, x in (("DEMA20", dema(c, 20)), ("TEMA20", tema(c, 20)), ("Hull20", hull(c, 20)),
                  ("KAMA", kama(c)), ("PSAR", psar(h, l)), ("Supertrend", line),
                  ("Ichimoku conv", conv), ("Vortex+", vp), ("Aroon up", au)):
        print(f"  {nm:<16}finite {100*np.isfinite(x).mean():>5.1f}%   "
              f"last {np.asarray(x, float)[-1]:,.2f}")
    print(f"  Supertrend direction: {100*(dr > 0).mean():.1f}% up")
    print(f"  {len(EMA_SET)} EMA periods, {len(EMA_PAIRS)} crossover pairs")
