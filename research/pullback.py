"""Follow the daily trend. Wait for a pullback. Enter on the resumption. 07:00-11:00 New York.

Structure, fixed before any search:

    SIDE      dictated by the DAILY trend, never chosen by the optimiser. This is the point of
              the whole design. On this sample a search allowed to pick a side picks long and
              gets paid for the 91% the index rose; here the rule is long because the daily trend
              is up, and it is short when it is not.
    PULLBACK  the market has moved AGAINST the daily trend on the intraday chart.
    RESUMPTION the pullback is ending -- this is what actually fires the order.
    WINDOW    entries only between 07:00 and 11:00 New York. Applied by masking trigger bars
              rather than as a rule condition, so it does not consume one of the three slots.

This is trend continuation, not mean reversion: the pullback is the discount, the resumption is
the entry, and the direction is the daily trend's. A rule that bought a dip in a daily DOWNTREND
would be the mean-reversion trade and cannot be expressed here.

Two honest limits of the sample, stated before the results:
  * 81% of intraday bars sit in a daily uptrend and 7% in a daily downtrend. The short side has
    very little data, so its numbers deserve much less weight than the long side's.
  * 07:00-09:30 is pre-RTH. Volume there is a fraction of the cash session and the spread is
    wider than the cost model assumes, which the cost-sensitivity test is there to probe.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from bos_choch import prep
from daily_trend import on_bars

WINDOW = (420, 660)            # 07:00 to 11:00 New York
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
FLATS = [0, 660, 720, 960]     # none, 11:00, 12:00, 16:00
EXITS = [(a, 1.0, f) for a in STOPS for f in FLATS]

UP_STATES = ["D close>EMA200", "D EMA20>EMA50", "D EMA50>EMA200", "D EMA20>EMA50>EMA200",
             "D uptrend + ADX>20", "D slope50>0", "D +DI>-DI"]
DN_STATES = ["D close<EMA200", "D EMA20<EMA50", "D EMA50<EMA200", "D EMA20<EMA50<EMA200",
             "D downtrend + ADX>20", "D slope50<0", "D -DI>+DI"]


def pullbacks(d, side):
    """The market has moved against the daily trend. `side` +1 for an uptrend, -1 for a downtrend."""
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    atr_ = np.maximum(d["atr"], 1e-9)
    e20, e50 = I.ema(c, 20), I.ema(c, 50)
    r14 = I.rsi(c, 14)
    kk, _dd = I.stoch(h, l, c)
    vw = I.session_vwap(h, l, c, v, d["sess"])
    up = np.r_[False, np.diff(c) > 0]
    S = {}
    if side == 1:
        S["below EMA20"] = c < e20
        S["below EMA50"] = c < e50
        S["below EMA20 by 0.5 ATR"] = (e20 - c) / atr_ > 0.5
        S["below EMA20 by 1 ATR"] = (e20 - c) / atr_ > 1.0
        S["below session VWAP"] = c < vw
        for n in (5, 10, 20):
            S[f"at {n}-bar low"] = c < I.shift(I.rmin(l, n))
        for k in (35, 40, 45):
            S[f"RSI<{k}"] = r14 < k
        S["Stoch K<20"] = kk < 20
        S["Stoch K<30"] = kk < 30
        S["2 down closes"] = (~up) & (I.shift((~up).astype(float), 1) > 0)
        S["3 down closes"] = ((~up) & (I.shift((~up).astype(float), 1) > 0)
                              & (I.shift((~up).astype(float), 2) > 0))
        S["retrace >1 ATR from 20-bar high"] = (I.shift(I.rmax(h, 20)) - c) / atr_ > 1.0
    else:
        S["above EMA20"] = c > e20
        S["above EMA50"] = c > e50
        S["above EMA20 by 0.5 ATR"] = (c - e20) / atr_ > 0.5
        S["above EMA20 by 1 ATR"] = (c - e20) / atr_ > 1.0
        S["above session VWAP"] = c > vw
        for n in (5, 10, 20):
            S[f"at {n}-bar high"] = c > I.shift(I.rmax(h, n))
        for k in (55, 60, 65):
            S[f"RSI>{k}"] = r14 > k
        S["Stoch K>80"] = kk > 80
        S["Stoch K>70"] = kk > 70
        S["2 up closes"] = up & (I.shift(up.astype(float), 1) > 0)
        S["3 up closes"] = (up & (I.shift(up.astype(float), 1) > 0)
                            & (I.shift(up.astype(float), 2) > 0))
        S["retrace >1 ATR from 20-bar low"] = (c - I.shift(I.rmin(l, 20))) / atr_ > 1.0
    return S


def resumptions(d, side):
    """The pullback is ending. This is the bar the order is sent on."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    e20 = I.ema(c, 20)
    r14 = I.rsi(c, 14)
    kk, _dd = I.stoch(h, l, c)
    up = np.r_[False, np.diff(c) > 0]
    S = {}
    if side == 1:
        S["cross back above EMA20"] = (c > e20) & (I.shift((c > e20).astype(float), 1) < 0.5)
        S["close > prior high"] = c > I.shift(h)
        S["close > 3-bar high"] = c > I.shift(I.rmax(h, 3))
        S["bullish engulfing"] = (c > I.shift(o)) & (o < I.shift(c)) & (c > o)
        S["first up close"] = up & (I.shift(up.astype(float), 1) < 0.5)
        S["RSI back above 40"] = (r14 > 40) & (I.shift(r14, 1) <= 40)
        S["RSI back above 50"] = (r14 > 50) & (I.shift(r14, 1) <= 50)
        S["Stoch K back above 20"] = (kk > 20) & (I.shift(kk, 1) <= 20)
        S["bullish bar"] = c > o
        S["close in top third of bar"] = (c - l) / np.maximum(h - l, 1e-9) > 0.667
    else:
        S["cross back below EMA20"] = (c < e20) & (I.shift((c < e20).astype(float), 1) > 0.5)
        S["close < prior low"] = c < I.shift(l)
        S["close < 3-bar low"] = c < I.shift(I.rmin(l, 3))
        S["bearish engulfing"] = (c < I.shift(o)) & (o > I.shift(c)) & (c < o)
        S["first down close"] = (~up) & (I.shift((~up).astype(float), 1) < 0.5)
        S["RSI back below 60"] = (r14 < 60) & (I.shift(r14, 1) >= 60)
        S["RSI back below 50"] = (r14 < 50) & (I.shift(r14, 1) >= 50)
        S["Stoch K back below 80"] = (kk < 80) & (I.shift(kk, 1) >= 80)
        S["bearish bar"] = c < o
        S["close in bottom third of bar"] = (c - l) / np.maximum(h - l, 1e-9) < 0.333
    return S


def pool(tf, side):
    """(names, boolean matrix, index ranges) for one side at one timeframe."""
    d = prep(tf)
    T = on_bars(d)
    st = [k for k in (UP_STATES if side == 1 else DN_STATES)]
    pb = pullbacks(d, side)
    rs = resumptions(d, side)
    names = st + list(pb) + list(rs)
    n = len(d["c"])
    M = np.zeros((len(names), n), np.bool_)
    for i, k in enumerate(st):
        M[i] = T[k]
    for i, k in enumerate(pb):
        M[len(st) + i] = np.nan_to_num(np.asarray(pb[k], float), nan=0.0) > 0.5
    for i, k in enumerate(rs):
        M[len(st) + len(pb) + i] = np.nan_to_num(np.asarray(rs[k], float), nan=0.0) > 0.5
    M[:, :300] = False
    win = (d["mod"] >= WINDOW[0]) & (d["mod"] < WINDOW[1])
    return d, names, M, (len(st), len(pb), len(rs)), win


if __name__ == "__main__":
    for tf in (5, 15, 30):
        d, names, M, (ns, npb, nrs), win = pool(tf, 1)
        rules = ns * npb * nrs
        print(f"{tf:>3}m  {ns} daily states x {npb} pullbacks x {nrs} resumptions = {rules:,} "
              f"rules per side")
        print(f"      {int(win.sum()):,} of {len(d['c']):,} bars in 07:00-11:00 "
              f"({100*win.mean():.1f}%), {int(win.sum())/765:.1f} per session")
    print(f"\n      x {len(EXITS)} geometries x 2 sides x 3 timeframes = "
          f"{rules * len(EXITS) * 2 * 3:,} combinations")
