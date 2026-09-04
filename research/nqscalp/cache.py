"""Memoised indicator pieces so a parameter sweep does not re-run the Python
recursions once per cell. The source arrays never change, only the periods do."""
import numpy as np, sys
sys.path.insert(0, "/home/user/main/research/nqscalp")
import nqs

_E, _R, _RSI, _ST, _HH, _LL, _SMA, _PCT = {}, {}, {}, {}, {}, {}, {}, {}


def build(df):
    o, h, l, c = (df[x].values.astype(float) for x in ("open", "high", "low", "close"))
    v = df["tickvol"].values.astype(float)
    tr = nqs.true_range(h, l, c)
    return dict(o=o, h=h, l=l, c=c, v=v, tr=tr)


def ema(B, n, kind="ema"):
    if (n, kind) not in _E: _E[(n, kind)] = nqs.ma(B["c"], n, kind)
    return _E[(n, kind)]

def atr(B, n):
    if n not in _R: _R[n] = nqs.rma(B["tr"], n)
    return _R[n]

def stoch_kd(B, rsi_len, stoch_len, k_s, d_s):
    key = (rsi_len, stoch_len, k_s, d_s)
    if key not in _ST:
        if rsi_len not in _RSI: _RSI[rsi_len] = nqs.rsi(B["c"], rsi_len)
        r = _RSI[rsi_len]
        lo, hi = nqs.ll(r, stoch_len), nqs.hh(r, stoch_len)
        with np.errstate(divide="ignore", invalid="ignore"):
            raw = np.where(hi - lo == 0, 0.0, 100 * (r - lo) / (hi - lo))
        k = nqs.sma(raw, k_s); d = nqs.sma(k, d_s)
        _ST[key] = (k, d)
    return _ST[key]

def atr_pct(B, atr_n, win):
    """Causal rank of the current ATR within its trailing window. Slow to build
    (a rolling apply over 206k bars), so it is built once per (atr_n, win)."""
    key = (atr_n, win)
    if key not in _PCT:
        import pandas as pd
        a = atr(B, atr_n)
        _PCT[key] = (pd.Series(a).rolling(win)
                     .apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True).values)
    return _PCT[key]


def swing(B, n):
    if n not in _HH: _HH[n] = nqs.hh(B["h"], n); _LL[n] = nqs.ll(B["l"], n)
    return _HH[n], _LL[n]

def sma_v(B, n):
    if n not in _SMA: _SMA[n] = nqs.sma(B["v"], n)
    return _SMA[n]


def indicators(df, B, **kw):
    """Same dict nqs.indicators returns, assembled from the cache."""
    p = {**nqs.DEFAULTS, **kw}
    k, d = stoch_kd(B, p["rsi_len"], p["stoch_len"], p["k_smooth"], p["d_smooth"])
    sh, sl = swing(B, p["pullback_lookback"])
    mf, ms = ema(B, p["macd_fast"]), ema(B, p["macd_slow"])
    macd = mf - ms
    I = dict(trend=ema(B, p["trend_ema"], p["trend_ma"]),
             fast=ema(B, p["fast_ema"], p["pull_ma"]),
             slow=ema(B, p["slow_ema"], p["pull_ma"]),
             atr=atr(B, p["atr_len"]), k=k, d=d,
             swing_hi=sh, swing_lo=sl, vol_avg=sma_v(B, p["vol_len"]),
             atr_pct=(atr_pct(B, p["atr_len"], p["atr_pct_len"])
                      if (p["atr_pct_max"] is not None or p["atr_pct_min"] is not None)
                      else np.full(len(B["c"]), np.nan)),
             macd=macd, macd_sig=nqs.ema(np.nan_to_num(macd, nan=0.0), p["macd_signal"]),
             o=B["o"], h=B["h"], l=B["l"], c=B["c"], v=B["v"])
    return I, p
