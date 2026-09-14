"""What does a trend-following SCALP actually need? One experiment, two geometries, one base.

THE QUESTION, MADE MEASURABLE. "Which indicators does a profitable trend-following scalp need" is
not answerable by listing indicators. It is answerable by taking one trend-following trigger and
asking, of each candidate condition, three things:

  1. ITS BASE RATE ON THE TRIGGER'S OWN BARS. A condition that passes 95% of the bars the trigger
     already fires on is the trigger restated and cannot help. This branch has measured that four
     times -- RSI(14)>=55 at 94.7%, Aroon osc>=0 at 100.0%, MACD>0 at 99.8-100.0%, MFI>=50 at
     91.7% -- and it is two lines of code that should precede any sweep.
  2. WHAT IT CONTRIBUTES AT SCALP GEOMETRY -- a tight stop, a near target, a hold measured in
     hours.
  3. WHAT IT CONTRIBUTES AT SWING GEOMETRY -- a wide stop, no target, a hold measured in days.

The third column is what makes the answer honest. A condition that helps at both is an edge; one
that helps only at swing geometry is telling you the geometry is the asset; one that helps at
neither is decoration. And the difference between the two columns is the actual answer to the
question asked.

Both triggers, both geometries, every condition, on three markets and every block.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit, prange

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "v63")):
    if p not in sys.path:
        sys.path.insert(0, p)

import indicators as I   # noqa: E402
import v63feeds as FD    # noqa: E402

# (stop ATR, target ATR, max hold bars). The scalp is a tight barrier pair with a two-hour cap;
# the swing is what every positive result on this branch has actually looked like.
GEOM = {"scalp": (0.75, 1.5, 24), "swing": (2.5, 0.0, 480)}
FEEDS = (("NQ", 5), ("NQ", 30), ("US100", 15), ("US100", 60), ("US30", 15), ("US30", 60))
FAST = {"NQ": 5, "US100": 15, "US30": 15}


def _wilder(x, n):
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(market, tf):
    f = FD.bars(market, tf)
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(c)
    ix = pd.DatetimeIndex(f.index)
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = _wilder(tr, 14)
    S = pd.Series(c)
    D = dict(market=market, tf=tf, n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, mod=mod, atr=atr, tr=tr)

    # ---- trend / location
    for p in (20, 50, 200):
        D[f"ema{p}"] = S.ewm(span=p, adjust=False).mean().to_numpy()
    D["sma200"] = S.rolling(200).mean().to_numpy()
    for a, b, cc in ((13, 34, 89),):
        e = [S.ewm(span=x, adjust=False).mean().to_numpy() for x in (a, b, cc)]
        D["stack"] = (e[0] > e[1]) & (e[1] > e[2])
    D["e13"] = S.ewm(span=13, adjust=False).mean().to_numpy()
    D["e48"] = S.ewm(span=48, adjust=False).mean().to_numpy()
    # session VWAP anchored 09:30 New York
    key = np.where(mod >= 570, (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy(),
                   (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy() - 1)
    tp = (h + l + c) / 3.0
    num = den = 0.0
    vw = np.empty(n)
    prev = key[0] - 1
    for i in range(n):
        if key[i] != prev:
            num = den = 0.0
            prev = key[i]
        num += tp[i] * v[i]
        den += v[i]
        vw[i] = num / den if den > 0 else np.nan
    D["vwap"] = vw

    # ---- momentum
    D["rsi"] = I.rsi(c, 14) if hasattr(I, "rsi") else _rsi(c, 14)
    D["macd"] = S.ewm(span=12, adjust=False).mean().to_numpy() - S.ewm(span=26, adjust=False).mean().to_numpy()
    D["macd_sig"] = pd.Series(D["macd"]).ewm(span=9, adjust=False).mean().to_numpy()
    D["roc20"] = np.concatenate((np.full(20, np.nan), c[20:] / c[:-20] - 1.0))
    D["mfi"] = I.mfi(h, l, c, v, 14)
    up = pd.Series(h).rolling(25).apply(lambda x: 25 - 1 - np.argmax(x), raw=True).to_numpy()
    dn = pd.Series(l).rolling(25).apply(lambda x: 25 - 1 - np.argmin(x), raw=True).to_numpy()
    D["aroon"] = 100.0 * (25 - up) / 25 - 100.0 * (25 - dn) / 25

    # ---- regime
    D["adx"] = _adx(h, l, c, 14)
    s = pd.Series(tr).rolling(14).sum().to_numpy()
    rng = (pd.Series(h).rolling(14).max() - pd.Series(l).rolling(14).min()).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        D["chop"] = 100.0 * np.log10(s / rng) / np.log10(14)
    move = np.abs(np.concatenate((np.full(20, np.nan), c[20:] - c[:-20])))
    path = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(20).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        D["er"] = move / path
    D["atr_mean"] = pd.Series(atr).rolling(50).mean().to_numpy()
    D["vol_pct"] = pd.Series(atr / c).rolling(250).rank(pct=True).to_numpy()

    # ---- volume / flow, and structure
    tod = pd.Series(v).groupby(mod).transform(lambda x: x.expanding().mean().shift(1)).to_numpy()
    D["vol_rel"] = v / np.where(np.isfinite(tod) & (tod > 0), tod, np.nan)
    D["clpos"] = np.where(h > l, (c - l) / np.maximum(h - l, 1e-12), 0.5)
    D["don20"] = pd.Series(h).rolling(20).max().shift(1).to_numpy()
    # prior completed RTH session high, frozen at the session end
    psh = np.full(n, np.nan)
    cur, H, last = -1, -np.inf, np.nan
    dk = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    for i in range(n):
        if dk[i] != cur:
            if H > -np.inf:
                last = H
            cur, H = dk[i], -np.inf
        if 570 <= mod[i] < 960:
            H = max(H, h[i])
        psh[i] = last
    D["psh"] = psh
    D["blocks"] = FD.blocks(market, ix)
    D["cost"], D["pv"] = FD.COST[market]
    D["slip"] = 1.0 * {"NQ": 0.25, "US100": 0.1, "US30": 0.1}[market]
    return D


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = _wilder(np.maximum(d, 0), n)
    dn = _wilder(np.maximum(-d, 0), n)
    return 100 - 100 / (1 + up / np.maximum(dn, 1e-12))


def _adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = _wilder(tr, n)
    pdi = 100 * _wilder(pdm, n) / np.maximum(a, 1e-12)
    ndi = 100 * _wilder(ndm, n) / np.maximum(a, 1e-12)
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return _wilder(dx, n)


# ------------------------------------------------------------------ the conditions
def conditions(D):
    """Every candidate, as a boolean over all bars, grouped by the family it belongs to."""
    c, h, atr = D["c"], D["h"], D["atr"]
    C = {}
    def add(fam, name, m):
        C[(fam, name)] = np.asarray(m, bool) & np.isfinite(atr) & (atr > 0)
    # TREND / DIRECTION
    add("trend", "close > EMA50", c > D["ema50"])
    add("trend", "close > SMA200", c > D["sma200"])
    add("trend", "EMA13 > EMA48", D["e13"] > D["e48"])
    add("trend", "EMA 13>34>89 stacked", D["stack"])
    add("trend", "(close-SMA200)/ATR >= 1", (c - D["sma200"]) / atr >= 1.0)
    add("trend", "close > session VWAP", c > D["vwap"])
    add("trend", "VWAP rising", D["vwap"] > np.concatenate(([np.nan], D["vwap"][:-1])))
    # MOMENTUM
    add("momentum", "RSI(14) >= 55", D["rsi"] >= 55)
    add("momentum", "RSI(14) >= 65", D["rsi"] >= 65)
    add("momentum", "MACD > 0", D["macd"] > 0)
    add("momentum", "MACD > signal", D["macd"] > D["macd_sig"])
    add("momentum", "ROC(20) > 0", D["roc20"] > 0)
    add("momentum", "MFI(14) >= 55", D["mfi"] >= 55)
    add("momentum", "Aroon osc >= 0", D["aroon"] >= 0)
    # REGIME
    add("regime", "ADX >= 20", D["adx"] >= 20)
    add("regime", "ADX >= 25", D["adx"] >= 25)
    add("regime", "CHOP <= 45", D["chop"] <= 45)
    add("regime", "CHOP <= 38", D["chop"] <= 38)
    add("regime", "efficiency ratio >= 0.3", D["er"] >= 0.30)
    add("regime", "ATR >= its 50-bar mean", atr >= D["atr_mean"])
    add("regime", "ATR <= its 50-bar mean", atr <= D["atr_mean"])
    add("regime", "vol pct(250) >= 0.5", D["vol_pct"] >= 0.5)
    add("regime", "vol pct(250) <= 0.5", D["vol_pct"] <= 0.5)
    # LOCATION / STRUCTURE
    add("location", "close in top 30% of bar", D["clpos"] >= 0.70)
    add("location", "close > prior RTH high", c > D["psh"])
    add("location", "(close-VWAP)/ATR >= 0.5", (c - D["vwap"]) / atr >= 0.5)
    add("location", "0 < (close-VWAP)/ATR <= 2", ((c - D["vwap"]) / atr > 0)
        & ((c - D["vwap"]) / atr <= 2.0))
    # PARTICIPATION
    add("volume", "volume >= its time-of-day mean", D["vol_rel"] >= 1.0)
    add("volume", "volume >= 1.5x that mean", D["vol_rel"] >= 1.5)
    # CLOCK
    add("clock", "09:30-11:00 New York", (D["mod"] >= 570) & (D["mod"] < 660))
    add("clock", "09:30-16:00 New York", (D["mod"] >= 570) & (D["mod"] < 960))
    return C


def triggers(D):
    t = {}
    hi = D["don20"]
    m = np.asarray(D["h"] > hi, bool).copy()
    t["Donchian 20 breakout"] = m
    st = D["stack"]
    fresh = st & ~np.concatenate(([False], st[:-1]))
    since = np.full(D["n"], 10 ** 6, np.int64)
    last = -10 ** 6
    for i in range(D["n"]):
        if fresh[i]:
            last = i
        since[i] = i - last
    t["EMA 13/34/89 stack, <=30 bars old"] = st & (since <= 30)
    return t


# ------------------------------------------------------------------ the walk
@njit(cache=True, parallel=True)
def walk(o, h, l, c, atr, rows, stop, tp, hold, cost, slip, m):
    N = len(rows)
    pts = np.full(N, np.nan)
    xb = np.full(N, -1, np.int64)
    for k in prange(N):
        i = rows[k]
        a = i + 1
        anc = atr[i]
        if a < 2 or a >= m - 3 or not np.isfinite(anc) or anc <= 0:
            continue
        px = o[a] + slip
        lvl = px - stop * anc
        tgt = px + tp * anc if tp > 0.0 else 1e18
        end = a + hold
        if end > m - 3:
            end = m - 3
        out = np.nan
        j = a
        while j <= end:
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip
                break
            if h[j] >= tgt:
                out = (tgt if o[j] < tgt else o[j]) - slip
                break
            j += 1
        if not np.isfinite(out):
            j = end
            out = c[j] - slip
        xb[k] = j
        pts[k] = out - px - cost
    return pts, xb


def lock(rows, keep, pts, xb, epx, blk):
    free, out = -1, []
    for k in keep:
        if xb[k] < 0 or not np.isfinite(pts[k]) or rows[k] <= free:
            continue
        free = xb[k]
        out.append((blk[rows[k]], 100.0 * pts[k] / epx[k]))
    return out
