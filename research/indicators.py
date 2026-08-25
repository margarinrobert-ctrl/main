"""An indicator library for the strategy generator. Every series is causal: the value at bar i
uses bars up to and including i, and never bar i+1."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _s(x):
    return pd.Series(np.asarray(x, float))


def ema(x, n):    return _s(x).ewm(span=n, adjust=False).mean().to_numpy()
def sma(x, n):    return _s(x).rolling(n).mean().to_numpy()
def rma(x, n):    return _s(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
def wma(x, n):    # linearly weighted, weight n on the newest observation down to 1
    w = np.arange(1, int(n) + 1, dtype=float)
    return _s(x).rolling(int(n)).apply(lambda v: float(np.dot(v, w) / w.sum()), raw=True).to_numpy()
def rmax(x, n):   return _s(x).rolling(n).max().to_numpy()
def rmin(x, n):   return _s(x).rolling(n).min().to_numpy()
def rstd(x, n):   return _s(x).rolling(n).std(ddof=0).to_numpy()
def rsum(x, n):   return _s(x).rolling(n).sum().to_numpy()
def shift(x, k=1):
    y = np.full(len(x), np.nan); y[k:] = np.asarray(x, float)[:-k]; return y
def rising(x):    return np.r_[False, np.diff(np.asarray(x, float)) > 0]


def true_range(h, l, c):
    pc = shift(c)
    return np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)


def rsi(c, n):
    d = np.r_[0.0, np.diff(np.asarray(c, float))]
    return 100 - 100 / (1 + rma(np.maximum(d, 0), n) / np.maximum(rma(np.maximum(-d, 0), n), 1e-12))


def stoch(h, l, c, n=14, k=3):
    hh, ll = rmax(h, n), rmin(l, n)
    kk = 100 * (c - ll) / np.maximum(hh - ll, 1e-12)
    return kk, sma(kk, k)


def adx_di(h, l, c, n=14):
    tr = true_range(h, l, c)
    up = np.r_[0.0, np.diff(np.asarray(h, float))]
    dn = np.r_[0.0, -np.diff(np.asarray(l, float))]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = rma(tr, n)
    pdi = 100 * rma(pdm, n) / np.maximum(atr, 1e-12)
    mdi = 100 * rma(mdm, n) / np.maximum(atr, 1e-12)
    dx = 100 * np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12)
    return rma(dx, n), pdi, mdi


def macd(c, f=12, s=26, g=9):
    line = ema(c, f) - ema(c, s)
    return line, ema(line, g)


def cci(h, l, c, n=20):
    tp = (h + l + c) / 3.0
    m = sma(tp, n)
    md = _s(tp).rolling(n).apply(lambda w: np.abs(w - w.mean()).mean(), raw=True).to_numpy()
    return (tp - m) / np.maximum(0.015 * md, 1e-12)


def willr(h, l, c, n=14):
    hh, ll = rmax(h, n), rmin(l, n)
    return -100 * (hh - c) / np.maximum(hh - ll, 1e-12)


def mfi(h, l, c, v, n=14):
    tp = (h + l + c) / 3.0
    raw = tp * np.asarray(v, float)
    up = np.where(tp > shift(tp), raw, 0.0)
    dn = np.where(tp < shift(tp), raw, 0.0)
    return 100 - 100 / (1 + rsum(up, n) / np.maximum(rsum(dn, n), 1e-12))


def bollinger(c, n=20, k=2.0):
    m, sd = sma(c, n), rstd(c, n)
    return m + k * sd, m, m - k * sd, 2 * k * sd / np.maximum(m, 1e-12)


def keltner(h, l, c, n=20, k=1.5):
    m = ema(c, n); a = rma(true_range(h, l, c), n)
    return m + k * a, m - k * a


def obv(c, v):
    d = np.sign(np.r_[0.0, np.diff(np.asarray(c, float))])
    return np.cumsum(d * np.asarray(v, float))


def trix(c, n=15):
    e = ema(ema(ema(c, n), n), n)
    return np.r_[0.0, np.diff(e)] / np.maximum(np.abs(e), 1e-12) * 100


def lin_slope(c, n):
    x = np.arange(n, dtype=float); x -= x.mean()
    den = (x * x).sum()
    return _s(c).rolling(n).apply(lambda w: float((x * (w - w.mean())).sum() / den),
                                  raw=True).to_numpy()


def roc(c, n):
    return 100 * (np.asarray(c, float) - shift(c, n)) / np.maximum(np.abs(shift(c, n)), 1e-12)


def session_vwap(h, l, c, v, sess):
    tp = (h + l + c) / 3.0 * np.asarray(v, float)
    out = np.empty(len(c)); num = 0.0; den = 0.0; prev = -1
    for i in range(len(c)):
        if sess[i] != prev:
            num = 0.0; den = 0.0; prev = sess[i]
        num += tp[i]; den += v[i]
        out[i] = num / den if den > 0 else np.nan
    return out


def prior_day(h, l, c, sess):
    """Yesterday's high, low and close, known from this session's first bar onward."""
    n = len(c)
    ph = np.full(n, np.nan); pl = np.full(n, np.nan); pc = np.full(n, np.nan)
    ch = -1e18; cl = 1e18; cc = np.nan; lh = np.nan; ll = np.nan; lc = np.nan; prev = -1
    for i in range(n):
        if sess[i] != prev:
            if prev != -1:
                lh, ll, lc = ch, cl, cc
            ch = -1e18; cl = 1e18; prev = sess[i]
        ph[i] = lh; pl[i] = ll; pc[i] = lc
        ch = max(ch, h[i]); cl = min(cl, l[i]); cc = c[i]
    return ph, pl, pc
