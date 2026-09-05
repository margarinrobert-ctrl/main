"""V53 -- LOWER-TIMEFRAME ABSORPTION, PARAMETER-FREE, and a deliberately small rule around it.

WHAT CHANGED FROM V51/V52, ALL AT THE USER'S DIRECTION:
  * Absorption is now just TWO readings -- buyer or seller -- and it is detected on a LOWER
    timeframe than the chart, automatically. On a 15-minute chart a 1-minute absorption inside the
    current bar is visible without switching charts.
  * ITS TWO TUNED NUMBERS ARE GONE. The volume-spike multiple and the close-inside-the-range
    fraction were both free parameters that a sweep can fit. They are replaced by the two natural
    values that cannot be tuned: volume at or above its OWN rolling mean (a ratio of 1.0), and the
    close on the wrong side of the bar's MIDPOINT (a fraction of 0.5). Nothing is left to choose
    except the mean's window, which is swept only to show the answer does not depend on it.
  * THE EMA 100 IS GONE, along with the ADX gate, the session windows, the flatten, the pyramid
    ladder and every "near/far" band except the two that were actually measured. What is left is
    the 200 EMA, the 13 and the 48.

THE 30-SECOND TIMEFRAME CANNOT BE TESTED HERE AND IS NOT PROXIED. The finest bars on this branch
are 1-minute (`data/NQ_1m.csv`). 30s absorption is left out of the research entirely; the Pine can
still request it, and that setting is therefore UNMEASURED and is labelled so.

CAUSALITY. A 1-minute absorption at T+3 inside a 15-minute bar starting at T is complete at T+4,
which is before the 15-minute bar closes at T+15 -- so reading it at the signal bar's close uses
only settled information. Absorption is never read from a lower-timeframe bar that has not closed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LTF = (1, 2, 3, 4, 5, 15)          # minutes; 30s is unavailable in this data and is NOT proxied
MEAN_W = (50, 100, 200)            # the only surviving number, swept to show it does not matter
TFS = (5, 15, 30, 60)


def load_1m(path="data/NQ_1m.csv"):
    d = pd.read_csv(path)
    ix = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                      "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                      "volume": d["volume"].to_numpy(float)}, index=ix)
    f = f.sort_index()
    return f[~f.index.duplicated(keep="first")]


def resample(f, tf):
    if tf == 1:
        return f
    return f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                       "close": "last", "volume": "sum"}).dropna()


def absorption(f, w):
    """PARAMETER-FREE. Volume at or above its own rolling mean, and the close on the wrong side of
    the bar's midpoint. Both thresholds are the natural value (1.0x and 0.5), not a fitted one.

    seller absorption -- buyers pushed the bar UP and the close came back BELOW the midpoint
    buyer  absorption -- sellers pushed the bar DOWN and the close came back ABOVE the midpoint
    """
    o = f["open"].to_numpy(float); h = f["high"].to_numpy(float)
    l = f["low"].to_numpy(float);  c = f["close"].to_numpy(float)
    v = f["volume"].to_numpy(float)
    base = pd.Series(v).rolling(w, min_periods=max(10, w // 4)).mean().shift(1).to_numpy()
    hv = np.isfinite(base) & (base > 0) & (v >= base)
    mid = 0.5 * (h + l)
    return (hv & (c > o) & (c < mid)), (hv & (c < o) & (c > mid))


def ltf_flags(f1, tf, w):
    """For each trading bar of size `tf`, did a buyer / seller absorption close INSIDE it, on each
    lower timeframe? Returns {ltf: (buy[n_bars], sell[n_bars])} aligned to the trading bars."""
    trade_ix = resample(f1, tf).index
    edges = trade_ix.values
    out = {}
    for m in LTF:
        if m > tf:
            continue
        g = resample(f1, m)
        sell, buy = absorption(g, w)
        # A lower-timeframe bar stamped t belongs to the trading bar it opens inside.
        owner = np.searchsorted(edges, g.index.values, side="right") - 1
        ok = owner >= 0
        b = np.zeros(len(edges), bool)
        s = np.zeros(len(edges), bool)
        np.logical_or.at(b, owner[ok & buy], True)
        np.logical_or.at(s, owner[ok & sell], True)
        out[m] = (b, s)
    return out


def recent(mask, k):
    if k <= 1:
        return np.asarray(mask, bool)
    return pd.Series(np.asarray(mask, float)).rolling(k, min_periods=1).max().to_numpy() > 0.5
