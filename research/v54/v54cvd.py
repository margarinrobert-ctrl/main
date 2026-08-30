"""V54 -- CVD divergence as a four-pattern structure test, a KAMA on an INDEPENDENT timeframe, and
a session window with a flatten.

=================================== WHAT CVD IS HERE, EXACTLY ===================================
TRUE cumulative volume delta needs the AGGRESSOR SIDE of every trade -- whether each contract lifted
the offer or hit the bid. No feed on this branch carries it. `data/NQ_1m.csv` is OHLCV, and the one
feed that ever had real taker-side flow (BTCUSDT's `Taker buy base`) is a different instrument and
is not attached.

So this is a PROXY, and the proxy is chosen to be the SAME ONE TRADINGVIEW USES. `ta.requestVolumeDelta`
signs each lower-timeframe bar's whole volume by that bar's own direction (close > open -> buying,
close < open -> selling) and accumulates. That is reproduced here on 1-minute bars. The consequence
is worth stating plainly rather than burying: this is not order flow, it is a direction-weighted
volume sum, and it will disagree with a real tick-delta feed. What makes it worth testing anyway is
that a TradingView user trading this signal would be trading THIS proxy -- so the research and the
script measure the same object.

============================ THE FOUR PATTERNS, AS SPECIFIED ============================
Compared at CONFIRMED SWING POINTS, never at arbitrary candles, and never with lookahead. A pivot at
bar i needs k bars on each side, so it is knowable only at bar i+k -- the divergence is therefore
stamped at the CONFIRMATION bar, not at the pivot. `STUDY_DIVERGENCE_CONFIRM` caught exactly this
leak once before: a feature that filled forward to the NEXT pivot's confirmation read +999 truncated
against +37 full.

  1 BULLISH_CVD_DIVERGENCE_EXHAUSTED_SELLERS   price LL + CVD HL
  2 BULLISH_CVD_ABSORPTION_SELLING_PRESSURE    price HL + CVD LL
  3 BEARISH_CVD_DIVERGENCE_EXHAUSTED_BUYERS    price HH + CVD LH
  4 BEARISH_CVD_ABSORPTION_BUYING_PRESSURE     price LH + CVD HH

The four are kept as four separate variables and tested independently. They are never collapsed into
one "CVD divergence" flag and CVD is never read as a directional indicator.

================================= THE KAMA, AND ITS CAVEAT =================================
Kaufman's Adaptive Moving Average replaces the 200 EMA, on an INDEPENDENT timeframe (60m or 240m)
regardless of the trading timeframe. The higher-timeframe value is sampled CAUSALLY: a trading bar
reads only the last HTF bar that has already CLOSED, which is the `lookahead_off` convention.

The caveat that belongs next to every KAMA result on this branch: `STUDY_MA_LAG` measured KAMA's
average lag at **1.25 bars regardless of window**, so its period is close to INERT on a trending
series. If the length axis turns out flat below, that is the expected result and not a failure of
the test.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PATTERNS = ("EXHAUSTED_SELLERS", "ABSORBED_SELLING", "EXHAUSTED_BUYERS", "ABSORBED_BUYING")
BULLISH = (0, 1)
BEARISH = (2, 3)


def cvd_1m(f1):
    """TradingView's rule: a lower-timeframe bar's whole volume is signed by its own direction."""
    o = f1["open"].to_numpy(float); c = f1["close"].to_numpy(float)
    v = f1["volume"].to_numpy(float)
    d = np.where(c > o, v, np.where(c < o, -v, 0.0))
    return np.cumsum(d)


def cvd_on(f1, cvd1, tf):
    """CVD sampled at each trading bar's CLOSE -- the running total as of that bar."""
    s = pd.Series(cvd1, index=f1.index)
    return s.resample(f"{tf}min").last().dropna()


def pivots(x, k):
    """Confirmed swing highs and lows. A pivot at i is knowable at i+k and NOT before.

    Returns (conf_bar, pivot_bar) pairs, so a caller can read the value AT the pivot while acting
    only at the confirmation."""
    n = len(x)
    hi, lo = [], []
    for i in range(k, n - k):
        w = x[i - k:i + k + 1]
        if x[i] == w.max() and np.argmax(w) == k:
            hi.append((i + k, i))
        if x[i] == w.min() and np.argmin(w) == k:
            lo.append((i + k, i))
    return hi, lo


def patterns(price_h, price_l, cvd, k, n):
    """The four patterns, each as its own boolean array stamped at the CONFIRMATION bar."""
    hi, lo = pivots(price_h, k)
    _hi2, lo2 = pivots(price_l, k)
    out = np.zeros((4, n), bool)

    prev = None
    for conf, piv in lo2:
        if conf >= n:
            break
        cur = (price_l[piv], cvd[piv])
        if prev is not None:
            p0, c0 = prev
            p1, c1 = cur
            if p1 < p0 and c1 > c0:
                out[0, conf] = True            # price LL + CVD HL
            if p1 > p0 and c1 < c0:
                out[1, conf] = True            # price HL + CVD LL
        prev = cur

    prev = None
    for conf, piv in hi:
        if conf >= n:
            break
        cur = (price_h[piv], cvd[piv])
        if prev is not None:
            p0, c0 = prev
            p1, c1 = cur
            if p1 > p0 and c1 < c0:
                out[2, conf] = True            # price HH + CVD LH
            if p1 < p0 and c1 > c0:
                out[3, conf] = True            # price LH + CVD HH
        prev = cur
    return out


def kama(x, n, fast=2, slow=30):
    """Kaufman's AMA. Efficiency ratio over n, smoothing constant between the fast and slow ends."""
    x = np.asarray(x, float)
    m = len(x)
    ch = np.abs(x - np.concatenate((np.full(n, np.nan), x[:-n]))) if m > n else np.full(m, np.nan)
    vol = pd.Series(np.abs(np.diff(x, prepend=x[0]))).rolling(n).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        er = np.where(vol > 0, ch / vol, 0.0)
    sc = (er * (2.0 / (fast + 1) - 2.0 / (slow + 1)) + 2.0 / (slow + 1)) ** 2
    out = np.full(m, np.nan)
    started = False
    for i in range(m):
        if not started:
            if np.isfinite(sc[i]) and np.isfinite(x[i]):
                out[i] = x[i]
                started = True
            continue
        # A single non-finite smoothing constant must not poison the rest of the series -- carry
        # the previous value instead. Leaving it NaN made KAMA 99.9% NaN on the first run here.
        out[i] = out[i - 1] if not np.isfinite(sc[i]) else out[i - 1] + sc[i] * (x[i] - out[i - 1])
    return out


def htf_causal(f1, tf, htf, n_kama):
    """KAMA computed on the HTF series and mapped down so a trading bar sees only CLOSED HTF bars.

    The map is `searchsorted` on HTF bar END times against trading bar END times, then one shift:
    the HTF bar that ends exactly at this trading bar's close is still usable, the one that has not
    ended is not."""
    g = f1["close"].resample(f"{htf}min").last().dropna()
    kv = kama(g.to_numpy(float), n_kama)
    end = g.index + pd.Timedelta(minutes=htf)          # the HTF bar closes here
    tix = f1["close"].resample(f"{tf}min").last().dropna().index + pd.Timedelta(minutes=tf)
    j = np.searchsorted(end.values, tix.values, side="right") - 1
    out = np.full(len(tix), np.nan)
    ok = j >= 0
    out[ok] = kv[j[ok]]
    return out
