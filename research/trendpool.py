"""The full trend-following pullback pool: every EMA, every crossover, and the rest of the kit.

Structure is unchanged from `pullback.py` -- daily trend state, then a pullback against it, then a
resumption trigger, entries 07:00-11:00 New York, direction dictated by the daily trend. What
changes is the size of each pool and, more importantly, THE NULL.

WHY THE NULL CHANGED. The first version gated on excess over the mean win rate of the RULE
POPULATION at each geometry. 1,158 rules cleared that, and then the time-matched control rejected
every one of them: the plain "be long in this window when the daily trend is up" baseline was
worth more than the rules were. A gate that admits rules a stronger null then rejects is not a
gate, it is a delay.

So the base rate here is the WINDOW BASELINE: what entering at every eligible bar inside
07:00-11:00 earns under the same side and geometry. A rule has to beat being in the market at
those times, which is the comparison that matters and the one that killed the last family.

No mean reversion is expressible: the pullback is always AGAINST the daily trend and the entry is
always WITH it.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
import trendind as T
from bos_choch import prep
from daily_trend import on_bars

WINDOW = (420, 660)
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
FLATS = [0, 660, 720, 960]
EXITS = [(a, 1.0, f) for a in STOPS for f in FLATS]


def _ind(d):
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    e = {n: I.ema(c, n) for n in T.EMA_SET}
    st_line, st_dir = T.supertrend(h, l, c)
    conv, base, sa, sb = T.ichimoku(h, l, c)
    vp, vm = T.vortex(h, l, c)
    au, ad = T.aroon(h, l)
    ml, msig = I.macd(c)
    adx, pdi, mdi = I.adx_di(h, l, c)
    ha_o, ha_c = T.heikin(o, h, l, c)
    return dict(e=e, st=st_dir, conv=conv, base=base, sa=sa, sb=sb, vp=vp, vm=vm,
                au=au, ad=ad, ml=ml, msig=msig, adx=adx, pdi=pdi, mdi=mdi,
                psar=T.psar(h, l), kama=T.kama(c), hull=T.hull(c, 20),
                ha_o=ha_o, ha_c=ha_c, rsi=I.rsi(c, 14), k=I.stoch(h, l, c)[0],
                vw=I.session_vwap(h, l, c, v, d["sess"]))


def trend_states(d, side, X=None):
    """Intraday trend agreement, on top of the DAILY state which is added separately."""
    c = d["c"]
    X = X or _ind(d)
    e = X["e"]
    up = side == 1
    S = {}
    for n in T.EMA_SET:
        S[f"close{'>' if up else '<'}EMA{n}"] = (c > e[n]) if up else (c < e[n])
    for a, b in T.EMA_PAIRS:
        S[f"EMA{a}{'>' if up else '<'}EMA{b}"] = (e[a] > e[b]) if up else (e[a] < e[b])
    S["Supertrend up" if up else "Supertrend down"] = (X["st"] > 0) if up else (X["st"] < 0)
    S["above Kijun" if up else "below Kijun"] = (c > X["base"]) if up else (c < X["base"])
    S["above cloud" if up else "below cloud"] = ((c > np.maximum(X["sa"], X["sb"])) if up
                                                 else (c < np.minimum(X["sa"], X["sb"])))
    S["PSAR below" if up else "PSAR above"] = (X["psar"] < c) if up else (X["psar"] > c)
    S["KAMA rising" if up else "KAMA falling"] = (I.rising(X["kama"]) if up
                                                  else ~I.rising(X["kama"]))
    S["Hull rising" if up else "Hull falling"] = (I.rising(X["hull"]) if up
                                                 else ~I.rising(X["hull"]))
    S["Vortex+ > Vortex-" if up else "Vortex- > Vortex+"] = ((X["vp"] > X["vm"]) if up
                                                             else (X["vm"] > X["vp"]))
    S["Aroon up > down" if up else "Aroon down > up"] = ((X["au"] > X["ad"]) if up
                                                         else (X["ad"] > X["au"]))
    S["MACD>signal" if up else "MACD<signal"] = ((X["ml"] > X["msig"]) if up
                                                 else (X["ml"] < X["msig"]))
    S["ADX>20 and +DI>-DI" if up else "ADX>20 and -DI>+DI"] = (
        (X["adx"] > 20) & ((X["pdi"] > X["mdi"]) if up else (X["mdi"] > X["pdi"])))
    S["LR slope50>0" if up else "LR slope50<0"] = ((I.lin_slope(c, 50) > 0) if up
                                                   else (I.lin_slope(c, 50) < 0))
    return S


def pullbacks(d, side, X=None):
    """Moved AGAINST the trend. Never an entry on its own."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_ = np.maximum(d["atr"], 1e-9)
    X = X or _ind(d)
    e = X["e"]
    up = side == 1
    S = {}
    for n in (5, 8, 9, 10, 12, 20, 21, 26, 34, 50):
        S[f"pull below EMA{n}" if up else f"pull above EMA{n}"] = (c < e[n]) if up else (c > e[n])
    for n in (20, 50):
        for k in (0.5, 1.0):
            nm = f"{'below' if up else 'above'} EMA{n} by {k} ATR"
            S[nm] = (((e[n] - c) / atr_ > k) if up else ((c - e[n]) / atr_ > k))
    S["below VWAP" if up else "above VWAP"] = (c < X["vw"]) if up else (c > X["vw"])
    for n in (3, 5, 10, 20):
        S[f"at {n}-bar low" if up else f"at {n}-bar high"] = (
            (c < I.shift(I.rmin(l, n))) if up else (c > I.shift(I.rmax(h, n))))
    for k in ((35, 40, 45, 50) if up else (50, 55, 60, 65)):
        S[f"RSI<{k}" if up else f"RSI>{k}"] = (X["rsi"] < k) if up else (X["rsi"] > k)
    for k in ((20, 30, 40) if up else (60, 70, 80)):
        S[f"Stoch<{k}" if up else f"Stoch>{k}"] = (X["k"] < k) if up else (X["k"] > k)
    dn = ~np.r_[False, np.diff(c) > 0] if up else np.r_[False, np.diff(c) > 0]
    f = dn.astype(float)
    S["2 against closes"] = dn & (I.shift(f, 1) > 0)
    S["3 against closes"] = dn & (I.shift(f, 1) > 0) & (I.shift(f, 2) > 0)
    S["4 against closes"] = dn & (I.shift(f, 1) > 0) & (I.shift(f, 2) > 0) & (I.shift(f, 3) > 0)
    for k in (0.5, 1.0, 1.5):
        S[f"retrace >{k} ATR"] = (((I.shift(I.rmax(h, 20)) - c) / atr_ > k) if up
                                  else ((c - I.shift(I.rmin(l, 20))) / atr_ > k))
    S["below Tenkan" if up else "above Tenkan"] = (c < X["conv"]) if up else (c > X["conv"])
    rng10 = I.rmax(h, 10) - I.rmin(l, 10)
    S["bottom third of 10-bar range" if up else "top third of 10-bar range"] = (
        ((c - I.rmin(l, 10)) / np.maximum(rng10, 1e-9) < 0.333) if up
        else ((c - I.rmin(l, 10)) / np.maximum(rng10, 1e-9) > 0.667))
    S["MACD histogram against"] = ((X["ml"] - X["msig"]) < 0) if up else ((X["ml"] - X["msig"]) > 0)
    S["touched EMA20"] = (l <= e[20]) & (h >= e[20])
    return S


def resumptions(d, side, X=None):
    """The pullback is ending. This bar sends the order."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_ = np.maximum(d["atr"], 1e-9)
    X = X or _ind(d)
    e = X["e"]
    up = side == 1
    S = {}
    for n in (9, 20, 21, 50):
        a = (c > e[n]) if up else (c < e[n])
        S[f"cross back {'above' if up else 'below'} EMA{n}"] = a & (I.shift(a.astype(float), 1) < 0.5)
    S["close beyond prior bar"] = (c > I.shift(h)) if up else (c < I.shift(l))
    for n in (2, 3, 5):
        S[f"close beyond {n}-bar extreme"] = ((c > I.shift(I.rmax(h, n))) if up
                                              else (c < I.shift(I.rmin(l, n))))
    S["engulfing"] = (((c > I.shift(o)) & (o < I.shift(c)) & (c > o)) if up
                      else ((c < I.shift(o)) & (o > I.shift(c)) & (c < o)))
    wu = np.r_[False, np.diff(c) > 0] if up else ~np.r_[False, np.diff(c) > 0]
    S["first with-trend close"] = wu & (I.shift(wu.astype(float), 1) < 0.5)
    S["2 with-trend closes"] = wu & (I.shift(wu.astype(float), 1) > 0)
    for k in ((40, 45, 50) if up else (60, 55, 50)):
        a = (X["rsi"] > k) if up else (X["rsi"] < k)
        S[f"RSI back {'above' if up else 'below'} {k}"] = a & (I.shift(a.astype(float), 1) < 0.5)
    for k in ((20, 30) if up else (80, 70)):
        a = (X["k"] > k) if up else (X["k"] < k)
        S[f"Stoch back {'above' if up else 'below'} {k}"] = a & (I.shift(a.astype(float), 1) < 0.5)
    hist = X["ml"] - X["msig"]
    S["MACD histogram turns"] = (hist > I.shift(hist)) if up else (hist < I.shift(hist))
    S["Heikin flips"] = ((X["ha_c"] > X["ha_o"]) & (I.shift((X["ha_c"] > X["ha_o"]).astype(float), 1) < 0.5)
                         if up else
                         (X["ha_c"] < X["ha_o"]) & (I.shift((X["ha_c"] < X["ha_o"]).astype(float), 1) < 0.5))
    S["close in far third of bar"] = (((c - l) / np.maximum(h - l, 1e-9) > 0.667) if up
                                      else ((c - l) / np.maximum(h - l, 1e-9) < 0.333))
    S["with-trend bar > 1 ATR"] = (((c > o) & ((h - l) > atr_)) if up
                                   else ((c < o) & ((h - l) > atr_)))
    a = (c > X["conv"]) if up else (c < X["conv"])
    S["cross Tenkan"] = a & (I.shift(a.astype(float), 1) < 0.5)
    S["Supertrend flips"] = ((X["st"] > 0) & (I.shift((X["st"] > 0).astype(float), 1) < 0.5) if up
                             else (X["st"] < 0) & (I.shift((X["st"] < 0).astype(float), 1) < 0.5))
    a = (X["psar"] < c) if up else (X["psar"] > c)
    S["PSAR flips"] = a & (I.shift(a.astype(float), 1) < 0.5)
    a = (c > X["vw"]) if up else (c < X["vw"])
    S["cross VWAP"] = a & (I.shift(a.astype(float), 1) < 0.5)
    return S


def pool(tf, side):
    d = prep(tf)
    X = _ind(d)
    D = on_bars(d)
    daily = [k for k in D if k.startswith("D ") and D[k].dtype == bool
             and (("close>" in k or ">EMA" in k or "uptrend" in k or "slope50>" in k
                   or "+DI>-DI" in k) if side == 1 else
                  ("close<" in k or "<EMA" in k or "downtrend" in k or "slope50<" in k
                   or "-DI>+DI" in k))]
    ts = trend_states(d, side, X)
    pb = pullbacks(d, side, X)
    rs = resumptions(d, side, X)
    st = {f"[daily] {k}": D[k] for k in daily}
    st.update(ts)
    names = list(st) + list(pb) + list(rs)
    n = len(d["c"])
    M = np.zeros((len(names), n), np.bool_)
    for i, k in enumerate(list(st) + list(pb) + list(rs)):
        src = st.get(k, pb.get(k, rs.get(k)))
        M[i] = np.nan_to_num(np.asarray(src, float), nan=0.0) > 0.5
    M[:, :300] = False
    win = (d["mod"] >= WINDOW[0]) & (d["mod"] < WINDOW[1])
    return d, names, M, (len(st), len(pb), len(rs)), win


if __name__ == "__main__":
    for side in (1, -1):
        d, names, M, (ns, npb, nrs), win = pool(30, side)
        print(f"{'long ' if side == 1 else 'short'}: {ns} trend states x {npb} pullbacks x "
              f"{nrs} resumptions = {ns*npb*nrs:,} rules")
    print(f"\nx {len(EXITS)} geometries x 2 sides x 3 timeframes = "
          f"{ns*npb*nrs*len(EXITS)*2*3:,} combinations")
