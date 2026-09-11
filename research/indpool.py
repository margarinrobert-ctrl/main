"""Indicators with the PERIOD as an argument, memoised, so a period is a knob and not a code edit.

`indicators.py` holds the primitive definitions and `trendind.py` the trend-following ones. Both
are called with explicit periods already -- but every condition POOL in this repository
(`alpha_factory2`, `alpha_ladder`) bakes the period into a NAME: `close>EMA10` is a string, so
asking "what if it were EMA 60" means editing a module and rebuilding a 115-column matrix.

This layer resolves `("ema", 60)` on demand and caches it on (bar set, name, args), which is what
makes a period sweep cost one vectorised pass per new value and nothing per re-use.

Nothing is redefined here that already exists. ATR is `ema(true_range, n)` and CCI is on hlc3,
both matching `bos_choch.atr` and the Pine emitters -- the two definitional traps that have
shipped broken once each.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indicators as I

_MEMO: dict = {}
REG: dict = {}
DOC: dict = {}


def ind(name, doc):
    def deco(f):
        REG[name] = f
        DOC[name] = doc
        return f
    return deco


def _atr(d, n=14):
    return I.ema(I.true_range(d["h"], d["l"], d["c"]), int(n))


def _safe(x, lo=1e-12):
    return np.where(np.abs(x) > lo, x, lo)


# ------------------------------------------------------------- one period argument
@ind("ema", "exponential moving average of close")
def _ema(d, n): return I.ema(d["c"], int(n))


@ind("sma", "simple moving average of close")
def _sma(d, n): return I.sma(d["c"], int(n))


@ind("wma", "linearly weighted moving average of close (LMA)")
def _wma(d, n): return I.wma(d["c"], int(n))


@ind("atr", "average true range, ema(tr, n)")
def _atr_r(d, n): return _atr(d, n)


@ind("natr", "atr as a percent of close")
def _natr(d, n): return 100.0 * _atr(d, n) / _safe(d["c"])


@ind("rsi", "relative strength index")
def _rsi(d, n): return I.rsi(d["c"], int(n))


@ind("rsichg", "one-bar change in RSI(n); >0 is RSI rising")
def _rsichg(d, n):
    r = I.rsi(d["c"], int(n))
    return r - I.shift(r)


@ind("stoch", "stochastic %K")
def _stoch(d, n): return I.stoch(d["h"], d["l"], d["c"], int(n))[0]


@ind("willr", "Williams %R")
def _willr(d, n): return I.willr(d["h"], d["l"], d["c"], int(n))


@ind("cci", "commodity channel index, on hlc3")
def _cci(d, n): return I.cci(d["h"], d["l"], d["c"], int(n))


@ind("mfi", "money flow index")
def _mfi(d, n): return I.mfi(d["h"], d["l"], d["c"], d["v"], int(n))


@ind("roc", "percent rate of change over n bars")
def _roc(d, n): return I.roc(d["c"], int(n))


@ind("mom", "close minus close n bars ago, in points")
def _mom(d, n): return d["c"] - I.shift(d["c"], int(n))


@ind("slope", "linear-regression slope of close over n bars")
def _slope(d, n): return I.lin_slope(d["c"], int(n))


@ind("std", "rolling standard deviation of close")
def _std(d, n): return I.rstd(d["c"], int(n))


@ind("bbw", "Bollinger band width, percent of the middle band")
def _bbw(d, n): return I.bollinger(d["c"], int(n))[3] * 100.0


@ind("zscore", "close in rolling standard deviations from its own mean")
def _z(d, n): return (d["c"] - I.sma(d["c"], int(n))) / _safe(I.rstd(d["c"], int(n)))


@ind("stretch", "EMASTRETCH: percent distance of close from EMA(n)")
def _stretch(d, n): return 100.0 * (d["c"] / _safe(I.ema(d["c"], int(n))) - 1.0)


@ind("emadist", "distance of close from EMA(n) in ATR(14) units")
def _emadist(d, n): return (d["c"] - I.ema(d["c"], int(n))) / _safe(_atr(d, 14))


@ind("emaslope", "one-bar change in EMA(n), in ATR(14) units")
def _emaslope(d, n):
    e = I.ema(d["c"], int(n))
    return (e - I.shift(e, 1)) / _safe(_atr(d, 14))


@ind("trix", "triple-smoothed ema rate of change")
def _trix(d, n): return I.trix(d["c"], int(n))


@ind("rvol", "volume over its own n-bar mean")
def _rvol(d, n): return d["v"] / _safe(I.sma(d["v"], int(n)))


@ind("adx", "average directional index")
def _adx(d, n): return I.adx_di(d["h"], d["l"], d["c"], int(n))[0]


@ind("pdi", "+DI")
def _pdi(d, n): return I.adx_di(d["h"], d["l"], d["c"], int(n))[1]


@ind("ndi", "-DI")
def _ndi(d, n): return I.adx_di(d["h"], d["l"], d["c"], int(n))[2]


@ind("di", "+DI minus -DI")
def _di(d, n):
    _, p, m = I.adx_di(d["h"], d["l"], d["c"], int(n))
    return p - m


@ind("hull", "Hull moving average")
def _hull(d, n):
    from trendind import hull
    return hull(d["c"], int(n))


@ind("kama", "Kaufman adaptive moving average")
def _kama(d, n):
    from trendind import kama
    return kama(d["c"], int(n))


@ind("dema", "double exponential moving average")
def _dema(d, n):
    from trendind import dema
    return dema(d["c"], int(n))


@ind("tema", "triple exponential moving average")
def _tema(d, n):
    from trendind import tema
    return tema(d["c"], int(n))


@ind("hh", "highest high of the n bars BEFORE this one")
def _hh(d, n): return I.shift(I.rmax(d["h"], int(n)), 1)


@ind("ll", "lowest low of the n bars BEFORE this one")
def _ll(d, n): return I.shift(I.rmin(d["l"], int(n)), 1)


@ind("rank", "percentile rank of close within the last n closes, 0-100")
def _rank(d, n):
    n = int(n); c = np.asarray(d["c"], float)
    out = np.full(len(c), 50.0)
    if len(c) >= n:
        from numpy.lib.stride_tricks import sliding_window_view
        w = sliding_window_view(c, n)
        out[n - 1:] = 100.0 * (w <= w[:, -1:]).mean(axis=-1)
    return out


@ind("keltpos", "close position across the n-bar Keltner channel, 0-100")
def _keltpos(d, n):
    u, lo = I.keltner(d["h"], d["l"], d["c"], int(n))
    return 100.0 * (d["c"] - lo) / _safe(u - lo)


# ------------------------------------------------------------- several arguments
@ind("macd", "MACD histogram in ATR(14) units: macd(fast, slow, signal)")
def _macd(d, f=12, s=26, g=9):
    line, sig = I.macd(d["c"], int(f), int(s), int(g))
    return (line - sig) / _safe(_atr(d, 14))


@ind("supertrend", "+1 up / -1 down: supertrend(period, multiplier)")
def _super(d, n=10, mult=3.0):
    from trendind import supertrend
    return np.asarray(supertrend(d["h"], d["l"], d["c"], int(n), float(mult))[1], float)


@ind("psar", "parabolic SAR level: psar(step, max)")
def _psar(d, step=0.02, mx=0.2):
    from trendind import psar
    return np.asarray(psar(d["h"], d["l"], float(step), float(mx)), float)


@ind("vortex", "VI+ minus VI-: vortex(n)")
def _vortex(d, n=14):
    from trendind import vortex
    p, m = vortex(d["h"], d["l"], d["c"], int(n))
    return p - m


@ind("aroon", "Aroon up minus Aroon down: aroon(n)")
def _aroon(d, n=25):
    from trendind import aroon
    u, dn = aroon(d["h"], d["l"], int(n))
    return u - dn


@ind("cross", "+1 the bar EMA(a) crosses above EMA(b), -1 below, else 0: cross(a, b)")
def _cross(d, a, b):
    x = np.sign(I.ema(d["c"], int(a)) - I.ema(d["c"], int(b)))
    out = np.zeros(len(x))
    out[1:] = np.where(x[1:] != x[:-1], x[1:], 0.0)
    return np.nan_to_num(out)


@ind("above", "close is above EMA(n) by at least k ATR(14): above(n, k)")
def _above(d, n, k=0.0):
    return ((d["c"] - I.ema(d["c"], int(n))) / _safe(_atr(d, 14)) >= float(k)).astype(float)


@ind("since", "bars since EMA(a) last crossed above EMA(b); large when no cross yet")
def _since(d, a, b):
    x = np.sign(I.ema(d["c"], int(a)) - I.ema(d["c"], int(b)))
    up = np.zeros(len(x), bool)
    up[1:] = (x[1:] > 0) & (x[:-1] <= 0)
    idx = np.where(up, np.arange(len(x)), -1)
    return (np.arange(len(x)) - np.maximum.accumulate(idx)).astype(float)


# ------------------------------------------------------------- no arguments
def _vwap(d):
    return I.session_vwap(d["h"], d["l"], d["c"], d["v"], d["sess"])


ZERO = {
    "close": lambda d: d["c"], "c": lambda d: d["c"],
    "open": lambda d: d["o"], "o": lambda d: d["o"],
    "high": lambda d: d["h"], "h": lambda d: d["h"],
    "low": lambda d: d["l"], "l": lambda d: d["l"],
    "volume": lambda d: d["v"], "v": lambda d: d["v"],
    "mod": lambda d: d["mod"].astype(float),
    "bar": lambda d: np.arange(len(d["c"]), dtype=float),
    "vwap": _vwap,
    "vwapd": lambda d: (d["c"] - _vwap(d)) / _safe(_atr(d, 14)),
    "body": lambda d: 100.0 * np.abs(d["c"] - d["o"]) / _safe(d["h"] - d["l"]),
    "pos": lambda d: 100.0 * (d["c"] - d["l"]) / _safe(d["h"] - d["l"]),
    "lowick": lambda d: 100.0 * (np.minimum(d["c"], d["o"]) - d["l"]) / _safe(d["h"] - d["l"]),
    "upwick": lambda d: 100.0 * (d["h"] - np.maximum(d["c"], d["o"])) / _safe(d["h"] - d["l"]),
    "green": lambda d: (d["c"] > d["o"]).astype(float),
    "range": lambda d: d["h"] - d["l"],
    "pdh": lambda d: I.prior_day(d["h"], d["l"], d["c"], d["sess"])[0],
    "pdl": lambda d: I.prior_day(d["h"], d["l"], d["c"], d["sess"])[1],
    "pdc": lambda d: I.prior_day(d["h"], d["l"], d["c"], d["sess"])[2],
}
ZERO_DOC = {
    "vwapd": "distance from session VWAP in ATR(14) units",
    "body": "body as a percent of the bar's range",
    "pos": "close position within the bar's range, 0-100",
    "lowick": "lower wick as a percent of the bar's range, 0-100",
    "upwick": "upper wick as a percent of the bar's range, 0-100",
    "mod": "minutes since New York midnight",
    "pdh": "prior day high", "pdl": "prior day low", "pdc": "prior day close",
}


def get(d, name, *args):
    """Memoised lookup. `d` must carry `_key`, a hashable id for its bar set."""
    key = (d["_key"], name, args)
    hit = _MEMO.get(key)
    if hit is not None:
        return hit
    if not args and name in ZERO:
        val = ZERO[name](d)
    elif name in REG:
        val = REG[name](d, *args)
    elif name in ZERO:
        raise TypeError(f"{name!r} takes no arguments")
    else:
        raise KeyError(f"unknown indicator {name!r}; try indpool.catalogue()")
    val = np.ascontiguousarray(np.asarray(val, float))
    _MEMO[key] = val
    return val


def catalogue():
    out = ["  no argument:"]
    for k in sorted(ZERO):
        out.append(f"    {k:<14}{ZERO_DOC.get(k,'')}")
    out.append("  one period argument, written ema200 or ema(200):")
    for k in sorted(REG):
        if k not in ("macd", "supertrend", "psar", "cross", "above", "since", "vortex", "aroon"):
            out.append(f"    {k:<14}{DOC[k]}")
    out.append("  several arguments, written name(a, b):")
    for k in ("macd", "supertrend", "psar", "vortex", "aroon", "cross", "above", "since"):
        out.append(f"    {k:<14}{DOC[k]}")
    return "\n".join(out)


def leak_check(tf=30, cut=0.7, tol=1e-6):
    """Truncate the bar series; every indicator must be unchanged before the cut.

    An indicator that reads forward -- a centred window, a whole-sample normalisation, a shift the
    wrong way -- changes its own history when the future is removed. `prior_day` and `vwap` are the
    ones worth watching, because both aggregate within a session and a session-final value written
    backwards would be invisible in any other test."""
    import fastbars
    b = fastbars.bars(tf)
    T = int(cut * b["n"])
    full = dict(b); full["_key"] = ("leak", tf, "full")
    trunc = {k: (v[:T] if isinstance(v, np.ndarray) else v) for k, v in b.items()}
    trunc["_key"] = ("leak", tf, "trunc")
    probes = [(n, (14,)) for n in REG
              if n not in ("macd", "supertrend", "psar", "cross", "above", "since")]
    probes += [("macd", (12, 26, 9)), ("supertrend", (10, 3.0)), ("psar", (0.02, 0.2)),
               ("cross", (9, 21)), ("above", (50, 0.5)), ("since", (9, 21))]
    probes += [(n, ()) for n in ZERO]
    bad = []
    for name, args in probes:
        a = get(full, name, *args)[:T]
        z = get(trunc, name, *args)
        m = np.isfinite(a) & np.isfinite(z)
        if m.sum() == 0:
            bad.append(f"{name}{args}: no finite overlap")
        elif not np.allclose(a[m], z[m], atol=tol, rtol=1e-6):
            bad.append(f"{name}{args}: max diff {np.abs(a[m] - z[m]).max():.3e}")
    return bad


if __name__ == "__main__":
    print(catalogue())
    bad = leak_check()
    print("\n  leakage across a 70% truncation:",
          "CLEAN" if not bad else "\n    " + "\n    ".join(bad))
