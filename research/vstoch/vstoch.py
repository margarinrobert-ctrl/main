"""VWAP + STOCHASTIC + ATR -- the design, declared before any search.

================================ WHAT THIS BRANCH ALREADY KNOWS ================================
Three components, and this branch has hard measurements on all three. The design is built around
them rather than around what the indicators are usually said to do.

 VWAP.  `STUDY_V63_TREND_VWAP` measured two things that change how it can be used.
        (1) THE VOLUME DOES NOTHING: over 69,003 matched pairs the volume-weighted anchor beat its
            UNWEIGHTED twin in 55.7% of them, mean +0.0096 Sharpe. A session average price does the
            same job, so nothing here may depend on a volume feed.
        (2) THE VWAP IS NOT SUPPORT: splitting that strategy's own trades by distance from the VWAP
            at entry, the NEAREST quartile was the WORST (+0.1325 against +0.2636 and +0.2538 for
            the two middle quartiles), the shape was a hump and not a gradient, and
            Spearman(distance, result) was -0.0495. What contributed was being on the right side of
            a RISING anchor -- a STATE, not a location.
        So the VWAP enters here as a STATE and its LOCATION readings are tested as declared
        alternatives rather than assumed. Both anchors are carried so the volume claim is re-checked
        on a new base.

 STOCHASTIC.  `STUDY_RULE_ANATOMY` found `Stoch K < 20` is EXACTLY `Williams %R < -80` -- one rule
        with two names -- so nothing is gained by adding Williams to the pool. `STUDY_DIVERGENCE_CONFIRM`
        measured Stoch divergence at +1.04 points against the +11.9 the geometry needed. Neither
        result says an oversold CROSS is worthless; both say it must be measured against a control.
        A stochastic reversal is a MEAN-REVERSION trigger, and mean reversion is the conclusion
        twelve separate routes on this branch have already reached -- which is the one honest reason
        to expect this family to behave differently from the breakouts that dominate the record.

 ATR.  `STUDY_V63` measured the direction: every FLOOR / RISING reading of ATR is positive as a
        regime filter (+0.006 to +0.047 mean edge) and every CEILING / FALLING reading is negative
        (-0.028 to -0.054). That INVERTS `STUDY_V28`, whose only survivor of 240 cells was the
        bottom fifth of ATR. Both directions are therefore run here, because a volatility rule whose
        sign has moved four times gets run both ways or not at all.
        `STUDY_V22` separately established the sizing rule: heat in ATR units is 1.8-2.2x larger in
        the LOW realised-volatility bucket, because ATR is backward-looking and volatility mean
        reverts, so `stop = 2.5N if vol percentile <= 0.5 else 1.5N`. That is carried as an option.

================================ THE DESIGN, FIXED BEFORE SEARCHING ================================
TRIGGER      Stochastic %K crosses above %D while %K is below an oversold floor (long), and the
             mirror for short. Declared, not searched: the CROSS is the event, the floor is a rung.
LOCATION     VWAP anchored at the 09:30 New York open, both volume-weighted and unweighted.
REGIME       ATR relative to its own trailing mean, tested as BOTH a floor and a ceiling.
EXIT         ATR stop, optional ATR target, hard hold cap. No take profit is the default because it
             has won eighteen times on this branch.
Long and short are both run: a mean-reversion trigger is symmetric in a way a breakout is not, and
`STUDY_V14_WINDOW_GRID` found the short side works precisely where the entry mechanic is a fade.

Every number below is measured on the RESEARCH block. The locked block is read once, at the end.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63", "research/v53"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import v63feeds as FD      # noqa: E402

SPLIT = 0.65
SLIP = {"NQ": 0.25, "US100": 0.10, "US30": 0.10}
OPEN_M = 9 * 60 + 30
CLOSE_M = 16 * 60


def _atr(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def stoch(h, l, c, k=14, d=3, smooth=3):
    """%K smoothed and %D. Standard construction; nothing bespoke."""
    hh = pd.Series(h).rolling(k).max().to_numpy()
    ll = pd.Series(l).rolling(k).min().to_numpy()
    raw = 100.0 * (c - ll) / np.maximum(hh - ll, 1e-12)
    K = pd.Series(raw).rolling(smooth).mean().to_numpy()
    Dv = pd.Series(K).rolling(d).mean().to_numpy()
    return K, Dv


def build(market, tf):
    f = FD.bars(market, tf)
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = f["volume"].to_numpy(float)
    ix = pd.DatetimeIndex(f.index)
    n = len(c)
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    rth = (mod >= OPEN_M) & (mod < CLOSE_M)

    # ---- session VWAP from the 09:30 open, through the CURRENT completed bar only.
    # Two anchors: volume-weighted, and the UNWEIGHTED session mean of the same typical price.
    # STUDY_V63 measured the volume as worth +0.0096 Sharpe, so both are carried and compared.
    tp = (h + l + c) / 3.0
    dfv = pd.DataFrame({"pv": np.where(rth, tp * v, 0.0), "v": np.where(rth, v, 0.0),
                        "tp": np.where(rth, tp, np.nan), "one": np.where(rth, 1.0, 0.0), "s": day})
    g = dfv.groupby("s", sort=False)
    vw = (g["pv"].cumsum() / g["v"].cumsum().replace(0, np.nan)).to_numpy()
    uw = (g["tp"].cumsum() / g["one"].cumsum().replace(0, np.nan)).to_numpy()
    vw[~rth] = np.nan
    uw[~rth] = np.nan

    atr = _atr(h, l, c)
    D = dict(market=market, tf=tf, n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, mod=mod, day=day,
             rth=rth, atr=atr, vwap=vw, vwap_uw=uw,
             cost=FD.COST[market][0], pv=FD.COST[market][1], slip=SLIP[market])
    # VWAP slope over 8 bars, scale-free
    for nm, s in (("vwap", vw), ("vwap_uw", uw)):
        sl = (s - np.concatenate((np.full(8, np.nan), s[:-8]))) / np.maximum(atr, 1e-12)
        D[nm + "_slope"] = sl
        D[nm + "_dist"] = (c - s) / np.maximum(atr, 1e-12)
    # ---- ATR regime, both directions available.
    # A PLAIN trailing mean is NOT a volatility baseline on a 24-hour tape. Measured here on NQ 15m:
    # mean ATR is 34.8 in the RTH hours against 13.1 overnight -- 2.7x -- so an RTH bar clears its own
    # 50-bar trailing mean 98.9% of the time and 25.1% of overnight bars do. `atr / rolling mean` is
    # then a TIME-OF-DAY indicator wearing a volatility name, and every rung of it is inert on any
    # session-restricted trigger. Same defect `STUDY_V32_FLOW_ML` fixed for volume by baselining
    # against an expanding time-of-day mean; the same repair is applied here.
    for w in (50, 100):
        D[f"atr_ratio{w}_raw"] = atr / np.maximum(
            pd.Series(atr).rolling(w).mean().to_numpy(), 1e-12)
    # CAUSAL time-of-day baseline: the mean ATR at this minute-of-day over PRIOR sessions only.
    ser = pd.Series(atr)
    gm = ser.groupby(mod)
    tod_mean = (gm.cumsum() - ser) / np.maximum(gm.cumcount().to_numpy(), 1)
    tod_mean = tod_mean.to_numpy()
    tod_mean[gm.cumcount().to_numpy() < 20] = np.nan
    D["atr_tod_mean"] = tod_mean
    D["atr_ratio_tod"] = atr / np.maximum(tod_mean, 1e-12)
    # and a causal time-of-day PERCENTILE RANK over the last 60 same-minute observations
    rk = ser.groupby(mod).apply(
        lambda x: x.shift(1).rolling(60, min_periods=20).rank(pct=True)).reset_index(level=0, drop=True)
    D["atr_tod_rank"] = rk.sort_index().to_numpy()
    for w in (50, 100):
        D[f"atr_ratio{w}"] = D[f"atr_ratio{w}_raw"]
    ap = pd.Series(atr / np.maximum(c, 1e-12))
    D["atr_pct_rank"] = ap.rolling(250).rank(pct=True).to_numpy()
    us = np.unique(day)
    D["cut_day"] = int(us[int(SPLIT * len(us))])
    D["blk"] = (day >= D["cut_day"]).astype(np.int64)
    D["last_bar"] = n - max(200, 20000 // tf)
    return D


def triggers(D, k=14, d=3, smooth=3, os_lvl=20.0, ob_lvl=80.0):
    """The declared trigger: %K crosses above %D while %K is below the oversold floor (long),
    and the mirror above the overbought ceiling (short). Both are stamped at the CROSS bar."""
    K, Dv = stoch(D["h"], D["l"], D["c"], k, d, smooth)
    up = (K > Dv) & (np.concatenate(([False], K[:-1] <= Dv[:-1])))
    dn = (K < Dv) & (np.concatenate(([False], K[:-1] >= Dv[:-1])))
    lo = up & (K < os_lvl)
    sh = dn & (K > ob_lvl)
    return np.nan_to_num(lo, nan=False).astype(bool), np.nan_to_num(sh, nan=False).astype(bool), K, Dv


@njit(cache=True)
def _walk(o, h, l, c, atr, gate, side, stop_n, tp_n, hold, cost, slip, first, last_bar):
    """One position at a time. Entry at the next open, ATR stop anchored at the SIGNAL bar,
    optional ATR target, hard hold cap. No channel exit -- this family has no channel."""
    m = len(c)
    cap = 40000
    sig = np.zeros(cap, np.int64); xb = np.zeros(cap, np.int64)
    pts = np.full(cap, np.nan); pct = np.full(cap, np.nan); R = np.full(cap, np.nan)
    why = np.zeros(cap, np.int64)
    cnt = 0; busy = -1
    for i in range(first, last_bar):
        if i <= busy or not gate[i]:
            continue
        a = i + 1
        anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        s = side
        px = o[a] + s * slip
        risk = stop_n * anchor
        stp = px - s * risk
        tgt = px + s * tp_n * anchor if tp_n > 0.0 else (1e18 if s > 0 else -1e18)
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan; j = a; w = 2
        while j <= end:
            if s > 0:
                if l[j] <= stp:
                    out = (stp if o[j] > stp else o[j]) - slip; w = 0; break
                if h[j] >= tgt:
                    out = (tgt if o[j] < tgt else o[j]) - slip; w = 1; break
            else:
                if h[j] >= stp:
                    out = (stp if o[j] < stp else o[j]) + slip; w = 0; break
                if l[j] <= tgt:
                    out = (tgt if o[j] > tgt else o[j]) + slip; w = 1; break
            j += 1
        if not np.isfinite(out):
            j = end; out = c[j] - s * slip; w = 2
        gg = s * (out - px) - cost
        if cnt < cap:
            sig[cnt] = i; xb[cnt] = j; pts[cnt] = gg
            pct[cnt] = 100.0 * gg / px; R[cnt] = gg / risk; why[cnt] = w
            cnt += 1
        busy = j
    return sig[:cnt], xb[:cnt], pts[:cnt], pct[:cnt], R[:cnt], why[:cnt]


def run(D, gate, side=1, stop=2.0, tp=0.0, hold=96, cost=None, slip=None):
    cost = D["cost"] if cost is None else cost
    slip = D["slip"] if slip is None else slip
    sig, xb, pts, pct, R, why = _walk(D["o"], D["h"], D["l"], D["c"], D["atr"],
                                      np.asarray(gate, np.bool_), int(side), float(stop),
                                      float(tp), int(hold), float(cost), float(slip),
                                      300, int(D["last_bar"]))
    return pd.DataFrame(dict(sig=sig, exit_bar=xb, pts=pts, pct=pct, R=R, why=why,
                             blk=D["blk"][sig], day=D["day"][sig], ts=D["ix"][sig]))


def stats(t):
    if len(t) == 0:
        return dict(n=0, pf=np.nan, pct=np.nan, tot=np.nan, win=np.nan, dd=np.nan, ret_dd=np.nan)
    p = t.pts.to_numpy()
    cum = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
    return dict(n=len(t), pf=float(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)),
                pct=float(t.pct.mean()), tot=float(t.pct.sum()),
                win=float(100 * (p > 0).mean()), dd=dd,
                ret_dd=float(p.sum() / max(dd, 1e-9)))
