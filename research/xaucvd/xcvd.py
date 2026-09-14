"""GOLD x DONCHIAN x CVD -- the feature layer.

================================ WHAT IS DIFFERENT ON GOLD ================================
CVD needs bars FINER than the chart. `STUDY_V54_CVD_KAMA` built it from 1-minute bars under a
30-minute chart -- 30 sub-bars per chart bar -- and recorded that NQ was the only feed with 1-minute
data, so no cross-market read was possible. Gold's finest feed here is 15-MINUTE, so the CVD has to
be built from 15m sub-bars under a coarser chart:

    60m  chart ->  4 sub-bars a bar   (a COARSE delta: four signs a bar)
    240m chart -> 16 sub-bars a bar   (closest here to V54's 30)

Both are run, and the resolution is reported next to every number, because a 4-sub-bar delta is a
materially cruder object than a 30-sub-bar one and the two are not interchangeable.

TWO CAVEATS THAT STAY ATTACHED TO EVERY CVD NUMBER HERE:
  1. It is a PROXY, the same one TradingView uses -- each sub-bar's whole volume signed by that
     sub-bar's own direction. It is not aggressor-side order flow; no feed on this branch has that.
  2. GOLD'S VOLUME IS TICK VOLUME, not contracts (`research/datasets.py`). So this proxy signs TICK
     COUNTS. On NQ it signed contract volume. That is a second, gold-specific degradation of the
     same object and it is why a null result here is weaker evidence against CVD than a null on NQ.

================================ WHAT THE BASE ALREADY IS ================================
`STUDY_XAU_TWO_LAYER` established that the Donchian breakout on gold is a BULL-MARKET DRIFT
EXPOSURE: 0 of 15 frozen geometry-side cells clear p<=0.10 on block A and 0 of 15 on block B, while
4 of 15 clear on block C where gold rose 167.8% -- and against a random entry with the same exits
the breakout wins on block C at p 0.000 and on 0 of 4 cells on A and 1 of 4 on B.

That sets the question this module has to answer, and it is NOT "does CVD improve gold Donchian".
It is: does a CVD feature clear a SAME-SELECTIVITY RANDOM FILTER on the blocks where the base has no
edge? A filter that only works on block C is the drift again, measured a second way.

================================ THE FOUR PATTERNS, SEPARATELY ================================
`STUDY_V55_AUTOMATED_CVD` measured what happens when they are pooled: adding ABSORBED SELLING to
EXHAUSTED SELLERS took the kept share from 21.5% to 41.8%, HALVED the edge and lost the locked block
at p 0.210. A union is diluted by its weaker member. The four are kept as four and never collapsed.

Pivots are stamped at the CONFIRMATION bar (a pivot at i needs i-k..i+k, so it is knowable at i+k).
`STUDY_DIVERGENCE_CONFIRM` caught the alternative once: a feature that filled forward to the next
pivot's confirmation read +999 truncated against +37 full.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/xau", "research/v54"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import xau_core as X      # noqa: E402
import v54cvd as V54      # noqa: E402

SUB_TF = 15               # gold's finest bar


def bars(tf, start=X.START):
    """Chart bars at `tf` minutes, plus the CVD built from 15-minute sub-bars."""
    f = X.load(start)
    g = f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()
    # --- CVD from the sub-bars, sampled at each chart bar's CLOSE (the running total as of that bar)
    cvd_sub = V54.cvd_1m(f)
    s = pd.Series(cvd_sub, index=f.index).resample(f"{tf}min").last()
    g = g.join(s.rename("cvd")).dropna()
    # --- per-bar delta and the sub-bar imbalance inside the chart bar
    d_sub = pd.Series(np.diff(cvd_sub, prepend=0.0), index=f.index)
    g["delta"] = d_sub.resample(f"{tf}min").sum().reindex(g.index)
    up = (f["close"] > f["open"]).astype(float)
    g["sub_up"] = up.resample(f"{tf}min").mean().reindex(g.index)   # share of sub-bars that closed up
    g["sub_n"] = up.resample(f"{tf}min").count().reindex(g.index)
    return g


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rank(x, n):
    return pd.Series(x).rolling(n).rank(pct=True).to_numpy()


def build(tf, ent=20, exN=20, start=X.START):
    """Bars + Donchian stacks + the CVD feature block. Everything causal, everything shifted."""
    g = bars(tf, start)
    o, h, l, c, v = (g[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    cvd = g["cvd"].to_numpy(float)
    dlt = g["delta"].to_numpy(float)
    ix = pd.DatetimeIndex(g.index)
    n = len(c)

    D = dict(tf=tf, n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, cvd=cvd, delta=dlt,
             atr=X._atr(h, l, c), sub_n=g["sub_n"].to_numpy(float),
             sub_up=g["sub_up"].to_numpy(float),
             mod=(ix.hour * 60 + ix.minute).to_numpy(),
             day=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy())
    sh, sl = pd.Series(h), pd.Series(l)
    emax = 121
    D["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, emax)])
    D["ent_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, emax)])
    D["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, 81)])
    D["ex_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, 81)])
    D["blk"] = np.full(n, -1, np.int64)
    for i, (nm, (a, b)) in enumerate(X.BLOCKS.items()):
        D["blk"][(ix >= a) & (ix <= b)] = i
    D["last_bar"] = n - max(200, 20000 // tf)
    return D


def features(D, ks=(2, 3, 5), ws=(10, 20, 30)):
    """The CVD feature block, read AT the signal bar. ~30 columns in six declared families."""
    c, h, l, o, v = D["c"], D["h"], D["l"], D["o"], D["v"]
    cvd, dlt, atr, n = D["cvd"], D["delta"], D["atr"], D["n"]
    F = {}

    # ---- family 1: the four divergence patterns, each separate, at three pivot widths
    for k in ks:
        P = V54.patterns(h, l, cvd, k, n)
        for pi, nm in enumerate(V54.PATTERNS):
            recent = np.zeros(n, bool)
            for w in ws:
                r = pd.Series(P[pi].astype(float)).rolling(w).max().to_numpy() > 0
                F[f"div.{nm.lower()}_k{k}_w{w}"] = r.astype(float)

    # ---- family 2: CVD trend / state
    for w in (10, 20, 50):
        F[f"cvd.slope{w}"] = (cvd - np.concatenate((np.full(w, np.nan), cvd[:-w]))) / np.maximum(
            pd.Series(np.abs(dlt)).rolling(w).sum().to_numpy(), 1e-9)
        F[f"cvd.z{w}"] = ((cvd - pd.Series(cvd).rolling(w).mean().to_numpy())
                          / np.maximum(pd.Series(cvd).rolling(w).std().to_numpy(), 1e-9))
    F["cvd.rank100"] = _rank(cvd, 100)
    F["cvd.above_ema20"] = (cvd > _ema(cvd, 20)).astype(float)

    # ---- family 3: the breakout bar's own flow
    F["flow.bar_delta_norm"] = dlt / np.maximum(v, 1e-9)                 # -1..+1, net direction share
    F["flow.sub_up"] = D["sub_up"]
    F["flow.delta_z50"] = ((dlt - pd.Series(dlt).rolling(50).mean().to_numpy())
                           / np.maximum(pd.Series(dlt).rolling(50).std().to_numpy(), 1e-9))
    F["flow.delta_pos"] = (dlt > 0).astype(float)

    # ---- family 4: CVD CONFIRMING the break (the opposite question to divergence)
    for w in (20, 55):
        pr_new = (h >= pd.Series(h).rolling(w).max().shift(1).to_numpy()).astype(float)
        cv_new = (cvd >= pd.Series(cvd).rolling(w).max().shift(1).to_numpy()).astype(float)
        F[f"conf.cvd_newhigh{w}"] = cv_new
        F[f"conf.both{w}"] = ((pr_new > 0) & (cv_new > 0)).astype(float)

    # ---- family 5: EFFICIENCY -- how much price moves per unit of net delta
    for w in (20, 50):
        dp = (c - np.concatenate((np.full(w, np.nan), c[:-w]))) / np.maximum(atr, 1e-9)
        dc = (cvd - np.concatenate((np.full(w, np.nan), cvd[:-w])))
        sc = pd.Series(np.abs(dlt)).rolling(w).sum().to_numpy()
        F[f"eff.px_per_delta{w}"] = dp / np.maximum(np.abs(dc) / np.maximum(sc, 1e-9), 1e-6)
        F[f"eff.delta_share{w}"] = dc / np.maximum(sc, 1e-9)

    # ---- family 6: context the CVD claims are conditional on
    F["ctx.excess"] = (h - D["ent_hi"][20 - 2]) / np.maximum(atr, 1e-9)
    F["ctx.close_pos"] = (c - l) / np.maximum(h - l, 1e-9)
    F["ctx.atr_rank250"] = _rank(atr / np.maximum(c, 1e-9), 250)
    F["ctx.vol_ratio"] = v / np.maximum(pd.Series(v).rolling(50).mean().to_numpy(), 1e-9)

    X_ = pd.DataFrame(F)
    return X_.replace([np.inf, -np.inf], np.nan)


def truncation_audit(D, XF, probes=40, seed=3, tf=None):
    """Recompute every feature on history that ENDS at bar i and require the value at i to match.
    The only honest leakage test on this branch -- and the one that caught the divergence
    fill-forward leak in STUDY_DIVERGENCE_CONFIRM."""
    rng = np.random.default_rng(seed)
    lo = max(3000, int(np.flatnonzero(D["blk"] == 1)[0]))
    idx = rng.choice(np.arange(lo, D["n"] - 5), size=probes, replace=False)
    bad, checked = [], 0
    for i in sorted(idx):
        cut = {k: (val[..., :i + 1] if isinstance(val, np.ndarray) and val.ndim == 2
                   else (val[:i + 1] if isinstance(val, (np.ndarray, pd.DatetimeIndex)) else val))
               for k, val in D.items()}
        cut["n"] = i + 1
        Xi = features(cut)
        a, b = XF.iloc[i], Xi.iloc[-1]
        for col in XF.columns:
            va, vb = a[col], b[col]
            if not np.isfinite(va) and not np.isfinite(vb):
                continue
            checked += 1
            if not np.isclose(va, vb, rtol=1e-6, atol=1e-8):
                bad.append((i, col, va, vb))
    return bad, checked, len(idx)
