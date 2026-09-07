"""The remaining requested feature families: what one instrument's OHLCV can and cannot give.

Requested were price, volume, order flow, volatility, market structure, session, options,
cross-asset, microstructure, anomalies and regimes. Six of those are buildable here, three are
buildable only as PROXIES that must be labelled as such, and two are not buildable at all. Saying
which is which is the useful part -- a feature named `delta` that is actually a tick-rule guess
from 1-minute bars will be trusted like real delta and it should not be.

BUILDABLE                price, volume, volatility, market structure, session, anomalies, regimes
PROXIES ONLY             spread (estimated from high-low or return autocovariance, not quoted),
                         order flow (tick rule on 1-minute bars, not trade-side data),
                         trade intensity (bar count and volume, not prints)
NOT BUILDABLE HERE       options / IV / VIX / GEX / gamma regime, and cross-asset

The estimators are the published ones rather than inventions: Corwin-Schultz and Roll for the
spread, Garman-Klass, Rogers-Satchell, Parkinson and Yang-Zhang for variance, Amihud and a Kyle
lambda proxy for impact. Each has known assumptions and each is named so those can be looked up.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I

NEEDS_DATA = {
    "options / IV / GEX / gamma regime":
        "no options chain here. Needs an NQ/SPX chain with strikes, expiries and greeks, or at "
        "minimum a VIX/VXN daily series for the IV-level features.",
    "cross-asset (ES, DXY, bonds, VIX)":
        "one instrument in data/. Needs ES, DX, ZN and VX bar files on the same clock; then "
        "rolling correlation, beta and lead-lag become one function each.",
    "true bid/ask spread and depth":
        "no quotes. The two spread features below are ESTIMATORS from bars and are named so.",
    "true order-flow delta and absorption":
        "no trade-side data. The delta features below apply the tick rule to 1-minute bars, "
        "which is a proxy whose error grows with bar size.",
}


def spread_estimators(d):
    """Corwin-Schultz (2012) high-low spread, and Roll (1984) from return autocovariance."""
    h, l, c = d["h"], d["l"], d["c"]
    F = {}
    hi2 = np.maximum(h, I.shift(h)); lo2 = np.minimum(l, I.shift(l))
    b = (np.log(np.maximum(h, 1e-12) / np.maximum(l, 1e-12)) ** 2
         + np.log(np.maximum(I.shift(h), 1e-12) / np.maximum(I.shift(l), 1e-12)) ** 2)
    g = np.log(np.maximum(hi2, 1e-12) / np.maximum(lo2, 1e-12)) ** 2
    k = 3 - 2 * np.sqrt(2.0)
    a = (np.sqrt(2 * b) - np.sqrt(b)) / k - np.sqrt(g / k)
    cs = 2 * (np.exp(a) - 1) / (1 + np.exp(a))
    F["Corwin-Schultz spread"] = np.where(np.isfinite(cs), np.maximum(cs, 0.0), np.nan)
    r = np.r_[0.0, np.diff(np.log(np.maximum(c, 1e-12)))]
    cov = pd.Series(r).rolling(50).apply(
        lambda w: np.cov(w[1:], w[:-1])[0, 1] if len(w) > 2 else np.nan, raw=True).to_numpy()
    F["Roll spread"] = 2 * np.sqrt(np.maximum(-cov, 0.0))
    return F


def variance_estimators(d):
    """Range-based variance estimators. Each uses information a close-to-close estimate throws away."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    lh, ll, lo_, lc = (np.log(np.maximum(x, 1e-12)) for x in (h, l, o, c))
    F = {}
    F["Parkinson vol"] = np.sqrt((lh - ll) ** 2 / (4 * np.log(2)))
    F["Garman-Klass vol"] = np.sqrt(np.maximum(
        0.5 * (lh - ll) ** 2 - (2 * np.log(2) - 1) * (lc - lo_) ** 2, 0.0))
    F["Rogers-Satchell vol"] = np.sqrt(np.maximum(
        (lh - lc) * (lh - lo_) + (ll - lc) * (ll - lo_), 0.0))
    rv = I.rsum(np.r_[0.0, np.diff(np.log(np.maximum(c, 1e-12)))] ** 2, 20)
    F["realised vol 20"] = np.sqrt(np.maximum(rv, 0.0))
    F["vol of vol 50"] = I.rstd(F["Garman-Klass vol"], 50)
    a = d["atr"]
    F["ATR expansion 5v50"] = I.sma(a, 5) / np.maximum(I.sma(a, 50), 1e-12)
    F["ATR compression 20v100"] = I.sma(a, 20) / np.maximum(I.sma(a, 100), 1e-12)
    return F


def orderflow_proxies(d):
    """TICK-RULE proxies. Not delta. The 1-minute sign is a guess at the aggressor side."""
    from features2 import _owner
    own, o1, h1, l1, c1, v1 = _owner(d)
    n = len(d["c"])
    ok = (own >= 0) & (own < n)
    ow = own[ok]
    dc = np.r_[0.0, np.diff(c1[ok])]
    sgn = np.sign(dc)
    sgn[sgn == 0] = np.nan
    sgn = pd.Series(sgn).ffill().fillna(0.0).to_numpy()

    def agg(x):
        out = np.zeros(n)
        np.add.at(out, ow, x)
        return out

    vol = agg(v1[ok])
    dlt = agg(sgn * v1[ok])
    F = {}
    F["tick-rule delta"] = dlt
    F["tick-rule delta / volume"] = dlt / np.maximum(vol, 1e-9)
    F["tick-rule delta z100"] = (dlt - I.sma(dlt, 100)) / np.maximum(I.rstd(dlt, 100), 1e-9)
    # absorption proxy: heavy volume that did NOT move price
    rng = np.maximum(d["h"] - d["l"], 1e-9)
    F["absorption proxy"] = (vol / np.maximum(I.sma(vol, 20), 1e-9)) / (rng / np.maximum(d["atr"], 1e-9))
    # aggression proxy: closed at the extreme of the bar on heavy volume
    F["aggressive buy proxy"] = ((d["c"] - d["l"]) / rng) * (vol / np.maximum(I.sma(vol, 20), 1e-9))
    F["aggressive sell proxy"] = ((d["h"] - d["c"]) / rng) * (vol / np.maximum(I.sma(vol, 20), 1e-9))
    F["trade intensity"] = vol / np.maximum(I.sma(vol, 50), 1e-9)
    F["Kyle lambda proxy"] = np.abs(np.r_[0.0, np.diff(d["c"])]) / np.maximum(vol, 1e-9)
    return F


def structure(d):
    """Market structure: swing distance, break of structure, liquidity sweeps."""
    h, l, c = d["h"], d["l"], d["c"]
    atr_ = np.maximum(d["atr"], 1e-9)
    ph, pl = d["ph"], d["pl"]
    F = {}
    F["dist last swing high / ATR"] = (c - pd.Series(ph).ffill().to_numpy()) / atr_
    F["dist last swing low / ATR"] = (c - pd.Series(pl).ffill().to_numpy()) / atr_
    sh = pd.Series(ph).ffill().to_numpy(); sl = pd.Series(pl).ffill().to_numpy()
    F["BOS up"] = (c > I.shift(sh)).astype(float)
    F["BOS down"] = (c < I.shift(sl)).astype(float)
    # liquidity sweep: traded through a swing then closed back inside
    F["sweep of highs"] = ((h > I.shift(sh)) & (c < I.shift(sh))).astype(float)
    F["sweep of lows"] = ((l < I.shift(sl)) & (c > I.shift(sl))).astype(float)
    F["swing range / ATR"] = (sh - sl) / atr_
    return F


def session(d):
    """Session structure. London/NY overlap is 08:00-11:30 New York for the equity index day."""
    mod = d["mod"]
    F = {}
    F["is NY open hour"] = ((mod >= 570) & (mod < 630)).astype(float)
    F["is London/NY overlap"] = ((mod >= 480) & (mod < 690)).astype(float)
    F["is pre-RTH"] = (mod < 570).astype(float)
    F["is 07:00-11:00"] = ((mod >= 420) & (mod < 660)).astype(float)
    F["minutes from NY open"] = (mod - 570).astype(float)
    return F


def anomalies(d):
    """Deviations large enough to be events rather than noise."""
    c, v = d["c"], d["v"]
    r = np.r_[0.0, np.diff(np.log(np.maximum(c, 1e-12)))]
    F = {}
    F["volume shock z100"] = (v - I.sma(v, 100)) / np.maximum(I.rstd(v, 100), 1e-9)
    F["return shock z100"] = (r - I.sma(r, 100)) / np.maximum(I.rstd(r, 100), 1e-9)
    a = d["atr"]
    F["ATR shock z100"] = (a - I.sma(a, 100)) / np.maximum(I.rstd(a, 100), 1e-9)
    F["abs return / ATR"] = np.abs(np.r_[0.0, np.diff(c)]) / np.maximum(a, 1e-9)
    return F


def build_all(d):
    F = {}
    for fn in (spread_estimators, variance_estimators, orderflow_proxies, structure,
               session, anomalies):
        F.update(fn(d))
    return {k: np.asarray(v, float) for k, v in F.items()}


def leakage_check(tf=30, cuts=(0.7,)):
    from bos_choch import prep
    import features2
    d = prep(tf)
    full = build_all(d)
    bad = []
    for f in cuts:
        T = int(f * len(d["c"]))
        dt = {k: (v[:T] if isinstance(v, np.ndarray) else v) for k, v in d.items()}
        dt["df"] = d["df"].iloc[:T]
        features2._C.clear()
        sub = build_all(dt)
        for k in full:
            a, b = full[k][:T], sub[k]
            m = np.isfinite(a) & np.isfinite(b)
            diff = int((np.abs(a[m] - b[m]) > 1e-8 * np.maximum(1, np.abs(a[m]))).sum())
            if diff > 0.001 * max(m.sum(), 1):
                bad.append((f, k, diff, int(m.sum())))
    features2._C.clear()
    return bad


if __name__ == "__main__":
    from bos_choch import prep
    d = prep(30)
    F = build_all(d)
    print(f"{len(F)} further features on {len(d['c']):,} 30m bars\n")
    for nm, fn in (("spread estimators (PROXY)", spread_estimators),
                   ("variance estimators", variance_estimators),
                   ("order flow (PROXY)", orderflow_proxies),
                   ("market structure", structure), ("session", session),
                   ("anomalies", anomalies)):
        ks = list(fn(d))
        print(f"  {nm} ({len(ks)}): " + ", ".join(k[:28] for k in ks))
    print(f"\n  NOT BUILDABLE from this repository's data:")
    for k, why in NEEDS_DATA.items():
        print(f"    {k}\n       {why}")
    bad = leakage_check()
    print(f"\n  leakage check: {'CLEAN' if not bad else bad[:4]}")
