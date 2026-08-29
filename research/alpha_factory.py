"""A strategy generator, with this branch's failure modes designed in rather than discovered.

The idea is the one Build Alpha popularised: do not hand the machine a strategy, hand it a
library of CONDITIONS and a library of EXITS, let it enumerate the combinations, and let a
validation pipeline decide what survives.

What makes that dangerous is exactly what this repository has spent its whole life measuring:
a large enough search finds a winner on any data. The findings that constrain this build:

  * search width is monotonically harmful -- at 225,792 configurations the best-of-143,536
    landed at the 13.4th percentile of out-of-sample P&L, and the research/locked rank
    correlation was -0.079. So the generator reports the SELECTION CURVE, not just its winner.
  * direction cannot be a free parameter on 2022-25 NQ -- every search handed a side picked
    longs and was fitting the index. So every rule is run long AND short and the asymmetry is
    reported, never optimised.
  * a passing walk-forward and a passing Monte Carlo cannot detect a regime bet (section 4c).
    So the null here is a MATCHED RANDOM STRATEGY with the same trade count, not a bootstrap.
  * win rate means nothing without the barrier bound 1/(1+R), and the bound does not apply when
    a time stop is present -- both are handled explicitly.

Everything is causal: a condition at bar i uses bars up to and including i, and fills happen at
the open of i+1.
"""
from __future__ import annotations

import sys
import time
from itertools import combinations

import numpy as np
from numba import njit

sys.path.insert(0, "research")
from bos_choch import prep

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK


# ---- the condition library -----------------------------------------------------------------
def ema(x, n):
    import pandas as pd
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def rma(x, n):
    import pandas as pd
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def roll_max(x, n):
    import pandas as pd
    return pd.Series(x).rolling(n).max().to_numpy()


def roll_min(x, n):
    import pandas as pd
    return pd.Series(x).rolling(n).min().to_numpy()


def roll_mean(x, n):
    import pandas as pd
    return pd.Series(x).rolling(n).mean().to_numpy()


def build_conditions(d):
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    mod, sess, atr_ = d["mod"], d["sess"], d["atr"]
    n = len(c)
    S = {}
    for k in (20, 50, 100, 200):
        S[f"close > EMA{k}"] = c > ema(c, k)
    S["EMA20 > EMA50"] = ema(c, 20) > ema(c, 50)
    S["EMA50 > EMA200"] = ema(c, 50) > ema(c, 200)
    S["EMA10 > EMA20"] = ema(c, 10) > ema(c, 20)

    dif = np.r_[0.0, np.diff(c)]
    up = rma(np.maximum(dif, 0), 14); dn = rma(np.maximum(-dif, 0), 14)
    rsi = 100 - 100 / (1 + up / np.maximum(dn, 1e-12))
    S["RSI14 < 30"] = rsi < 30
    S["RSI14 > 70"] = rsi > 70
    S["RSI14 > 50"] = rsi > 50

    hh = roll_max(h, 14); ll = roll_min(l, 14)
    k_ = 100 * (c - ll) / np.maximum(hh - ll, 1e-12)
    d_ = roll_mean(k_, 3)
    S["Stoch K < 20"] = k_ < 20
    S["Stoch K > 80"] = k_ > 80
    S["Stoch K > D"] = k_ > d_

    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[c[0], c[:-1]]),
                                      np.abs(l - np.r_[c[0], c[:-1]])))
    pdm = np.maximum(np.r_[0.0, np.diff(h)], 0); mdm = np.maximum(-np.r_[0.0, np.diff(l)], 0)
    pdm[pdm <= mdm] = 0; mdm[mdm < pdm] = 0
    atr14 = rma(tr, 14)
    pdi = 100 * rma(pdm, 14) / np.maximum(atr14, 1e-12)
    mdi = 100 * rma(mdm, 14) / np.maximum(atr14, 1e-12)
    adx = rma(100 * np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12), 14)
    S["ADX > 20"] = adx > 20
    S["ADX > 25"] = adx > 25
    S["ADX rising"] = np.r_[False, np.diff(adx) > 0]
    S["+DI > -DI"] = pdi > mdi

    a20 = roll_mean(atr_, 20)
    S["ATR > 1.2x its 20 mean"] = atr_ > 1.2 * a20
    S["ATR < 0.8x its 20 mean"] = atr_ < 0.8 * a20
    S["ATR rising"] = np.r_[False, np.diff(atr_) > 0]

    for k in (10, 20, 50):
        S[f"close > {k}-bar high"] = c > np.r_[np.nan, roll_max(h, k)[:-1]]
        S[f"close < {k}-bar low"] = c < np.r_[np.nan, roll_min(l, k)[:-1]]

    rngb = np.maximum(h - l, 1e-12)
    S["body > 60% of range"] = np.abs(c - o) / rngb > 0.6
    S["bullish bar"] = c > o
    S["2 up closes"] = np.r_[False, False, (np.diff(c)[1:] > 0) & (np.diff(c)[:-1] > 0)]
    S["inside bar"] = np.r_[False, (h[1:] < h[:-1]) & (l[1:] > l[:-1])]
    S["outside bar"] = np.r_[False, (h[1:] > h[:-1]) & (l[1:] < l[:-1])]

    vm = roll_mean(v, 20)
    S["volume > 1.5x mean"] = v > 1.5 * vm
    S["volume < 0.7x mean"] = v < 0.7 * vm

    S["first hour"] = (mod >= 570) & (mod < 630)
    S["midday"] = (mod >= 690) & (mod < 810)
    S["last hour"] = (mod >= 900) & (mod < 960)

    e200 = ema(c, 200)
    dist = np.abs(c - e200) / np.maximum(atr_, 1e-12)
    S["far from EMA200 (>1 ATR)"] = dist > 1.0
    S["near EMA200 (<0.5 ATR)"] = dist < 0.5

    names = list(S)
    M = np.zeros((len(names), n), np.bool_)
    for i, k in enumerate(names):
        x = np.asarray(S[k])
        x[~np.isfinite(np.nan_to_num(x.astype(float), nan=0.0))] = False
        M[i] = np.nan_to_num(x.astype(float), nan=0.0) > 0.5
    M[:, :250] = False                       # warm-up: no indicator is trusted before bar 250
    return names, M


# ---- phase 1: what happens if you enter at bar i under exit geometry g ----------------------
@njit(cache=True)
def price_all(o, h, l, c, atr_, mod, side, atr_mult, tp_r, flat_min, ex_bar, ex_pnl, ok):
    n = len(c)
    for i in range(n - 1):
        a = atr_[i]
        if np.isnan(a) or a <= 0.0:
            ok[i] = 0
            continue
        entry = o[i + 1]
        st = entry - side * atr_mult * a
        tg = entry + side * tp_r * atr_mult * a
        j = i + 1
        done = 0
        while j < n:
            hit = (l[j] <= st) if side == 1 else (h[j] >= st)
            won = (h[j] >= tg) if side == 1 else (l[j] <= tg)
            if hit:
                px = o[j] if ((side == 1 and o[j] < st) or (side == -1 and o[j] > st)) else st
                px += -SE if side == 1 else SE
                ex_bar[i] = j; ex_pnl[i] = side * (px - entry) * PV - COMM - 2.0 * EC * PV
                ok[i] = 1; done = 1; break
            if won:
                px = o[j] if ((side == 1 and o[j] > tg) or (side == -1 and o[j] < tg)) else tg
                ex_bar[i] = j; ex_pnl[i] = side * (px - entry) * PV - COMM - 2.0 * EC * PV
                ok[i] = 2; done = 1; break
            if flat_min > 0 and mod[j] >= flat_min:
                ex_bar[i] = j; ex_pnl[i] = side * (c[j] - entry) * PV - COMM - 2.0 * EC * PV
                ok[i] = 3; done = 1; break
            j += 1
        if done == 0:
            ok[i] = 0


# ---- phase 2: walk a rule's trigger bars, one position at a time -----------------------------
@njit(cache=True)
def walk(trig, ex_bar, ex_pnl, ok, sidx, cut, out, row):
    cnt = np.zeros(2, np.int64); net = np.zeros(2, np.float64)
    wins = np.zeros(2, np.int64); gw = np.zeros(2, np.float64); gl = np.zeros(2, np.float64)
    eq = np.zeros(2, np.float64); pk = np.zeros(2, np.float64); dd = np.zeros(2, np.float64)
    tgt = np.zeros(2, np.int64)
    free = -1
    for k in range(len(trig)):
        i = trig[k]
        if i < free or ok[i] == 0:
            continue
        free = ex_bar[i]
        p = ex_pnl[i]
        b = 0 if sidx[i] < cut else 1
        cnt[b] += 1; net[b] += p
        if p > 0:
            wins[b] += 1; gw[b] += p
        else:
            gl[b] -= p
        if ok[i] == 2:
            tgt[b] += 1
        eq[b] += p
        if eq[b] > pk[b]:
            pk[b] = eq[b]
        if pk[b] - eq[b] > dd[b]:
            dd[b] = pk[b] - eq[b]
    for b in range(2):
        out[row, b * 7 + 0] = cnt[b]; out[row, b * 7 + 1] = net[b]
        out[row, b * 7 + 2] = wins[b]; out[row, b * 7 + 3] = gw[b]
        out[row, b * 7 + 4] = gl[b]; out[row, b * 7 + 5] = dd[b]
        out[row, b * 7 + 6] = tgt[b]


# ---- the driver ------------------------------------------------------------------------------
EXITS = [(1.5, 1.0, 0), (1.5, 2.0, 0), (1.0, 2.0, 0), (2.0, 3.0, 0),
         (2.0, 1.0, 960), (2.0, 2.0, 960)]


def main(tf=30, max_k=3, seed=20260823):
    t0 = time.time()
    d = prep(tf)
    names, M = build_conditions(d)
    n = M.shape[1]
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us = np.unique(d["sess"])
    sidx = np.searchsorted(us, d["sess"])
    cut = np.int64(int(0.65 * len(us)))

    rules = []
    for k in range(1, max_k + 1):
        rules.extend(combinations(range(len(names)), k))
    variants = [(s, e) for s in (1, -1) for e in range(len(EXITS))]
    total = len(rules) * len(variants)
    print(f"{len(names)} conditions -> {len(rules):,} rules x {len(variants)} "
          f"(2 directions x {len(EXITS)} exit geometries) = {total:,} strategies")

    # phase 1
    P1 = {}
    for s in (1, -1):
        for gi, (am, tp, fl) in enumerate(EXITS):
            eb = np.zeros(n, np.int64); ep = np.zeros(n); okk = np.zeros(n, np.int64)
            price_all(o, h, l, c, atr_, mod, s, am, tp, fl, eb, ep, okk)
            P1[(s, gi)] = (eb, ep, okk)
    print(f"   phase 1 done, {time.time()-t0:.0f}s", flush=True)

    out = np.zeros((total, 14))
    meta = np.zeros((total, 3), np.int64)
    row = 0
    for ri, r in enumerate(rules):
        m = M[r[0]].copy()
        for j in r[1:]:
            m &= M[j]
        trig = np.flatnonzero(m).astype(np.int64)
        for (s, gi) in variants:
            eb, ep, okk = P1[(s, gi)]
            if len(trig):
                walk(trig, eb, ep, okk, sidx, cut, out, row)
            meta[row] = (ri, s, gi)
            row += 1
        if ri % 2000 == 0:
            print(f"   {ri:>6,} / {len(rules):,} rules   {time.time()-t0:6.0f}s", flush=True)
    np.save("results/alpha/af_out.npy", out); np.save("results/alpha/af_meta.npy", meta)
    import pickle
    with open("results/alpha/af_rules.pkl", "wb") as f:
        pickle.dump((names, rules, EXITS), f)
    print(f"done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
