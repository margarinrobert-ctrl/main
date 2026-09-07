"""A continuous feature library, built only from what this repository actually has: OHLCV.

Every series is causal -- the value at bar i uses bars up to and including i and never i+1, and
`leakage_check` proves it by recomputing on truncated history rather than asserting it.

These are FEATURES, not conditions. alpha_factory2 turns market state into 115 booleans for rule
search; this turns it into ~60 real-valued series that can be ranked, correlated, clustered and
fed to a model. The two are complementary and share definitions where they overlap.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I


def _z(x, n):
    s = pd.Series(x, dtype=float)
    m = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return ((s - m) / sd.replace(0, np.nan)).to_numpy()


def _pctrank(x, n):
    s = pd.Series(x, dtype=float)
    return s.rolling(n).apply(lambda w: (w[-1] > w[:-1]).mean(), raw=True).to_numpy()


def _hurst(c, win=256, step=32):
    """Aggregated-variance Hurst, on a coarse grid and held forward. H > 0.5 trends, H < 0.5
    reverts. Computed every `step` bars because a rolling exact estimate over a million bars
    costs more than the information is worth."""
    r = np.diff(np.log(np.maximum(c, 1e-9)), prepend=np.log(max(c[0], 1e-9)))
    out = np.full(len(c), np.nan)
    scales = np.array([1, 2, 4, 8, 16])
    for i in range(win, len(c), step):
        w = r[i - win:i]
        v = []
        for s_ in scales:
            k = (len(w) // s_) * s_
            agg = w[:k].reshape(-1, s_).sum(axis=1)
            v.append(np.var(agg) if len(agg) > 2 else np.nan)
        v = np.array(v)
        ok = np.isfinite(v) & (v > 0)
        if ok.sum() >= 3:
            sl = np.polyfit(np.log(scales[ok]), np.log(v[ok]), 1)[0]
            out[i:i + step] = sl / 2.0
    return out


def _entropy(c, win=64, word=3):
    """Shannon entropy of `word`-bar up/down patterns, normalised to [0, 1]. Low entropy means
    the recent sign sequence is repetitive; high means it looks like a coin."""
    up = (np.diff(c, prepend=c[0]) > 0).astype(np.int64)
    code = np.zeros(len(c), np.int64)
    for k in range(word):
        code += np.roll(up, k) << k
    code[:word] = 0
    out = np.full(len(c), np.nan)
    n_sym = 1 << word
    counts = np.zeros(n_sym)
    for i in range(len(c)):
        counts[code[i]] += 1
        if i >= win:
            counts[code[i - win]] -= 1
            p = counts[counts > 0] / win
            out[i] = -(p * np.log2(p)).sum() / word
    return out


def build(d):
    """d is a prep() dict. Returns {name: series}, all causal, all real-valued."""
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    atr_, mod, sess = d["atr"], d["mod"], d["sess"]
    idx = d["df"].index
    F = {}
    rng_ = np.maximum(h - l, 1e-9)

    # ---- returns over horizons, raw and volatility-adjusted --------------------------------
    sd20 = I.rstd(np.r_[0.0, np.diff(c)], 20)
    for n in (1, 2, 5, 10, 20, 50, 100):
        r = c - I.shift(c, n)
        F[f"return {n}b"] = r
        F[f"return {n}b / vol"] = r / np.maximum(sd20 * np.sqrt(n), 1e-9)
        F[f"return {n}b / ATR"] = r / np.maximum(atr_, 1e-9)

    # ---- momentum and its acceleration -------------------------------------------------------
    for n in (10, 20):
        roc = I.roc(c, n)
        F[f"ROC{n}"] = roc
        F[f"ROC{n} acceleration"] = roc - I.shift(roc, n)
    F["LR slope20"] = I.lin_slope(c, 20) / np.maximum(atr_, 1e-9)
    F["LR slope50"] = I.lin_slope(c, 50) / np.maximum(atr_, 1e-9)

    # ---- volatility level, shape and regime --------------------------------------------------
    a20 = I.sma(atr_, 20); a100 = I.sma(atr_, 100)
    F["ATR / ATR20"] = atr_ / np.maximum(a20, 1e-9)
    F["ATR20 / ATR100"] = a20 / np.maximum(a100, 1e-9)          # expansion vs compression
    F["ATR z100"] = _z(atr_, 100)
    F["range / ATR"] = rng_ / np.maximum(atr_, 1e-9)
    F["range z50"] = _z(rng_, 50)
    bu, bm, bl, bw = I.bollinger(c)
    F["BB width"] = bw
    F["BB width / mean50"] = bw / np.maximum(I.sma(bw, 50), 1e-9)
    F["BB position"] = (c - bl) / np.maximum(bu - bl, 1e-9)
    F["realised vol 50 / 200"] = I.rstd(np.r_[0.0, np.diff(c)], 50) / \
        np.maximum(I.rstd(np.r_[0.0, np.diff(c)], 200), 1e-9)

    # ---- trend structure ----------------------------------------------------------------------
    e20, e50, e200 = I.ema(c, 20), I.ema(c, 50), I.ema(c, 200)
    F["dist EMA20 / ATR"] = (c - e20) / np.maximum(atr_, 1e-9)
    F["dist EMA50 / ATR"] = (c - e50) / np.maximum(atr_, 1e-9)
    F["dist EMA200 / ATR"] = (c - e200) / np.maximum(atr_, 1e-9)
    F["EMA20-EMA50 / ATR"] = (e20 - e50) / np.maximum(atr_, 1e-9)
    F["EMA50-EMA200 / ATR"] = (e50 - e200) / np.maximum(atr_, 1e-9)
    ad, pdi, mdi = I.adx_di(h, l, c)
    F["ADX"] = ad
    F["DI spread"] = pdi - mdi
    F["Donchian20 position"] = (c - I.rmin(l, 20)) / np.maximum(I.rmax(h, 20) - I.rmin(l, 20), 1e-9)
    F["Donchian50 position"] = (c - I.rmin(l, 50)) / np.maximum(I.rmax(h, 50) - I.rmin(l, 50), 1e-9)

    # ---- oscillators as levels, not thresholds ------------------------------------------------
    F["RSI14"] = I.rsi(c, 14)
    F["RSI14 - 50"] = I.rsi(c, 14) - 50.0
    kk, dd_ = I.stoch(h, l, c)
    F["Stoch K"] = kk; F["Stoch K-D"] = kk - dd_
    F["CCI20"] = I.cci(h, l, c)
    F["Williams %R"] = I.willr(h, l, c)
    F["MFI14"] = I.mfi(h, l, c, v)
    ml, msig = I.macd(c)
    F["MACD / ATR"] = ml / np.maximum(atr_, 1e-9)
    F["MACD histogram / ATR"] = (ml - msig) / np.maximum(atr_, 1e-9)

    # ---- VWAP -----------------------------------------------------------------------------------
    vw = I.session_vwap(h, l, c, v, sess)
    F["dist VWAP / ATR"] = (c - vw) / np.maximum(atr_, 1e-9)
    F["dist VWAP z100"] = _z((c - vw) / np.maximum(atr_, 1e-9), 100)

    # ---- volume and liquidity --------------------------------------------------------------------
    vm20 = I.sma(v, 20)
    F["volume / mean20"] = v / np.maximum(vm20, 1e-9)
    F["volume z50"] = _z(v, 50)
    F["volume acceleration"] = v / np.maximum(I.shift(v), 1e-9) - 1.0
    F["OBV slope20"] = I.lin_slope(I.obv(c, v), 20)
    F["dollar volume"] = v * c
    # Amihud illiquidity: how far price moves per unit of volume. High means thin.
    F["illiquidity"] = np.abs(np.r_[0.0, np.diff(c)]) / np.maximum(v, 1.0)
    F["illiquidity z100"] = _z(F["illiquidity"], 100)
    F["range per volume"] = rng_ / np.maximum(v, 1.0)

    # ---- candle shape -----------------------------------------------------------------------------
    F["body fraction"] = np.abs(c - o) / rng_
    F["upper wick fraction"] = (h - np.maximum(c, o)) / rng_
    F["lower wick fraction"] = (np.minimum(c, o) - l) / rng_
    F["gap / ATR"] = (o - I.shift(c)) / np.maximum(atr_, 1e-9)
    F["close position in bar"] = (c - l) / rng_

    # ---- statistical shape -------------------------------------------------------------------------
    ret = np.r_[0.0, np.diff(c)]
    F["skew 100"] = pd.Series(ret).rolling(100).skew().to_numpy()
    F["kurtosis 100"] = pd.Series(ret).rolling(100).kurt().to_numpy()
    F["autocorr 50"] = pd.Series(ret).rolling(50).apply(
        lambda w: pd.Series(w).autocorr(1) if np.std(w) > 0 else 0.0, raw=False).to_numpy()
    F["Hurst 256"] = _hurst(c)
    F["sign entropy 64"] = _entropy(c)
    F["close z100"] = _z(c, 100)
    F["close percentile 100"] = _pctrank(c, 100)
    F["variance ratio 5"] = (I.rstd(c - I.shift(c, 5), 100) ** 2) / \
        np.maximum(5 * I.rstd(ret, 100) ** 2, 1e-9)

    # ---- session and clock ---------------------------------------------------------------------------
    F["minutes since 09:30"] = (mod - 570).astype(float)
    F["time of day sin"] = np.sin(2 * np.pi * mod / 1440.0)
    F["time of day cos"] = np.cos(2 * np.pi * mod / 1440.0)
    F["day of week"] = np.array([t.dayofweek for t in idx], float)
    ph, pl_, pc = I.prior_day(h, l, c, sess)
    F["dist prior day high / ATR"] = (c - ph) / np.maximum(atr_, 1e-9)
    F["dist prior day low / ATR"] = (c - pl_) / np.maximum(atr_, 1e-9)
    F["prior day range / ATR"] = (ph - pl_) / np.maximum(atr_, 1e-9)
    sh = pd.Series(h).groupby(sess).cummax().to_numpy()
    sl = pd.Series(l).groupby(sess).cummin().to_numpy()
    F["session range / ATR"] = (sh - sl) / np.maximum(atr_, 1e-9)
    F["position in session range"] = (c - sl) / np.maximum(sh - sl, 1e-9)

    for k in F:
        F[k] = np.asarray(F[k], float)
    return F


NOT_AVAILABLE = {
    "order flow": "the file is OHLCV. Bid/ask, trade prints and the book are not in it.",
    "open interest": "not distributed with the bar file; a separate CME series.",
    "options / IV / Greeks / gamma exposure": "no options chain in this repository.",
    "market breadth": "a cross-sectional measure over an index's members. One instrument here.",
    "intermarket / cross-asset": "one instrument. ES, CL, GC, VX and the dollar are not present.",
    "futures basis": "needs the spot index alongside the future. Only the future is here.",
}


def leakage_check(tf=30, cuts=(0.4, 0.7)):
    """Recompute every feature on truncated history. A causal feature takes the same value at
    bar i < T whether or not the bars after T exist."""
    from bos_choch import prep
    d = prep(tf)
    F = build(d)
    n = len(d["c"])
    bad = []
    for f in cuts:
        T = int(f * n)
        dt = {k: (x[:T] if isinstance(x, np.ndarray) else x) for k, x in d.items()}
        dt["df"] = d["df"].iloc[:T]
        G = build(dt)
        for k in F:
            a, b = F[k][300:T], G[k][300:T]
            m = np.isfinite(a) & np.isfinite(b)
            if m.sum() and not np.allclose(a[m], b[m], atol=1e-8):
                bad.append((k, T, int((~np.isclose(a[m], b[m], atol=1e-8)).sum())))
    return F, bad


if __name__ == "__main__":
    F, bad = leakage_check()
    print(f"{len(F)} features")
    if bad:
        print(f"NOT CAUSAL: {len(bad)} feature/cut combinations differ on truncated history")
        for k, T, n in bad[:10]:
            print(f"   {k}  at T={T}: {n} bars differ")
    else:
        print("every feature identical when recomputed on truncated history -- all causal")
    print("\nNOT BUILDABLE from this repository's data:")
    for k, why in NOT_AVAILABLE.items():
        print(f"   {k:<42}{why}")
