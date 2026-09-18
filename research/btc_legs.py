"""All NINE shipped legs on BTC -- the first instrument where every one of them can be tested.

WHY ALL NINE. The EURUSD file is 30-minute, so the three 15-minute legs (V3, V4, M3) could not run
there. BTC's source is 15-minute, so the 15m legs run natively and the 30m legs run on a resample.

WHAT THIS TEST IS AND IS NOT. It is a transfer test of rules selected on NQ index futures onto a
24/7 crypto market. Three things differ from every previous cross-instrument check here, and all
three cut AGAINST the rules rather than for them:

  * THERE IS NO WEEKEND AND NO SESSION. Weekday bar counts are flat. Six of the nine legs carry a
    clock condition ("first hour", "first 120m") and all nine carry a flatten time, and those were
    written against a market that closes. On BTC they select an arbitrary slice of a continuous
    tape. That is a fair test of whether the rule's edge was ever about the session -- but a
    failure here does NOT prove the rule is broken on instruments that do have one.
  * THE VOLATILITY REGIME IS DIFFERENT BY AN ORDER OF MAGNITUDE. Scoring is in R units, which
    normalises for that, but the cost model cannot be inherited and is stated below.
  * CORRELATION WITH THE INDICES IS ONLY +0.13 at 15 minutes. That is the point -- it is close to
    an independent draw -- but it also means there is no prior reason an index rule should work.

COSTS. Binance spot taker fee is 0.10% per side and this feed carries no bid/ask, so the spread is
assumed at 1 basis point per side -- generous for BTCUSDT, which is one of the most liquid pairs in
existence. Total round turn 0.202%. That is charged in price terms and divided by the barrier, the
same arithmetic every other study here uses, and `run(fee_bp=...)` re-runs it at any assumption.

Scored against a MINUTE-OF-DAY MATCHED CONTROL and corrected together at BH q=0.10, as on EURUSD.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
from edgelab import crypto

TP_R = 1.0
MAX_HOLD = 400
TAKER_BP = 10.0      # 0.10% per side, Binance spot taker
SPREAD_BP = 1.0      # assumed half-spread per side, generous for BTCUSDT


def btc_bars(tf=15, atr_n=14):
    return crypto.bars("BTC", tf, atr_n=atr_n)


@njit(cache=True)
def _walk(o, h, l, c, atr, mod, trig, side, am, flat, tp_r, max_hold, cost_frac):
    """Barrier walk in R units. Costs are a FRACTION OF PRICE, charged once per side."""
    n = len(c); m = len(trig)
    R = np.zeros(m); why = np.zeros(m, np.int64)
    k = 0
    for t in range(m):
        i = trig[t]
        if i + 1 >= n or atr[i] <= 0.0:
            continue
        e = i + 1
        entry = o[e] * (1.0 + side * cost_frac)
        risk = am * atr[i]
        stop = entry - side * risk
        target = entry + side * tp_r * risk
        j = e
        r = 0.0; w = 4
        while j < n and (j - e) < max_hold:
            hit = (l[j] <= stop) if side == 1 else (h[j] >= stop)
            won = (h[j] >= target) if side == 1 else (l[j] <= target)
            if hit:
                px = stop * (1.0 - side * cost_frac)
                r = side * (px - entry) / risk; w = 1
                break
            if won:
                px = target * (1.0 - side * cost_frac)
                r = side * (px - entry) / risk; w = 2
                break
            if flat > 0 and mod[j] >= flat:
                px = c[j] * (1.0 - side * cost_frac)
                r = side * (px - entry) / risk; w = 3
                break
            j += 1
        if w == 4:
            jj = j if j < n else n - 1
            r = side * (c[jj] * (1.0 - side * cost_frac) - entry) / risk
        R[k] = r; why[k] = w; k += 1
    return R[:k], why[:k]


def _cost(fee_bp=TAKER_BP, spread_bp=SPREAD_BP):
    return (fee_bp + spread_bp) / 1e4


def run(d, mask, side, am, flat, fee_bp=TAKER_BP, spread_bp=SPREAD_BP):
    m = np.asarray(mask).copy(); m[:300] = False
    trig = np.flatnonzero(m & np.isfinite(d["atr"]) & (d["atr"] > 0)).astype(np.int64)
    R, why = _walk(d["o"], d["h"], d["l"], d["c"], d["atr"], d["mod"].astype(np.int64),
                   trig, side, am, flat, TP_R, MAX_HOLD, _cost(fee_bp, spread_bp))
    return trig, R, why


def control(d, trig, side, am, flat, draws=300, seed=17, fee_bp=TAKER_BP, spread_bp=SPREAD_BP):
    mod = d["mod"].astype(np.int64)
    ok = np.isfinite(d["atr"]) & (d["atr"] > 0)
    by = {}
    for i in range(300, len(d["c"]) - 1):
        if ok[i]:
            by.setdefault(int(mod[i]), []).append(i)
    want = {}
    for i in trig:
        want[int(mod[i])] = want.get(int(mod[i]), 0) + 1
    pools = {k: np.asarray(v, np.int64) for k, v in by.items() if k in want}
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    cf = _cost(fee_bp, spread_bp)
    for s in range(draws):
        pick = [rng.choice(pools[k], size=cnt, replace=True)
                for k, cnt in want.items() if k in pools and len(pools[k])]
        if not pick:
            out[s] = np.nan; continue
        tt = np.sort(np.concatenate(pick)).astype(np.int64)
        R, _w = _walk(d["o"], d["h"], d["l"], d["c"], d["atr"], mod, tt, side, am, flat,
                      TP_R, MAX_HOLD, cf)
        out[s] = R.mean() if len(R) else np.nan
    return out[np.isfinite(out)]


def leg_masks(tf, verbose=True):
    """Every shipped leg whose native timeframe is `tf`, rebuilt on BTC bars of that timeframe."""
    import indicators as I
    from oner_union import FAMILIES
    from alpha_ladder import build_ladder

    d = btc_bars(tf)
    o, h, l, c, mod = d["o"], d["h"], d["l"], d["c"], d["mod"]
    body = np.abs(c - o) / np.maximum(h - l, 1e-12)
    out = {}
    if tf == 30:
        out["V1"] = dict(mask=FAMILIES["V1"]["fn"](d, 1.2, 0.7, 5), side=1, am=3.0, flat=900)
        out["V2"] = dict(mask=FAMILIES["V2"]["fn"](d, (20, 50), 0.2, 120), side=-1, am=1.0, flat=960)
        bull = (c > I.shift(o)) & (o < I.shift(c)) & (c > o) & (body >= 0.2)
        out["V2L"] = dict(mask=(I.ema(c, 20) < I.ema(c, 50)) & bull & (mod >= 570) & (mod < 690),
                          side=1, am=2.5, flat=900)
        ladder = (("M1", ("ATR>1.2x mean", "bullish engulfing", "upper wick>60%"), 1, 1.0, 900),
                  ("M2", ("EMA20>EMA50", "bearish engulfing", "first hour"), -1, 1.0, 900),
                  ("M4", ("body<30%", "first hour", "ATR>1.8x mean"), 1, 4.0, 960))
    else:
        out["V3"] = dict(mask=FAMILIES["V3"]["fn"](d, 5, 0.0, 180), side=1, am=4.0, flat=960)
        out["V4"] = dict(mask=FAMILIES["V4"]["fn"](d, 20, 50, 0.5), side=-1, am=3.0, flat=960)
        ladder = (("M3", ("close>SMA100", "first hour", "Stoch K<25"), -1, 2.0, 960),)

    names, M = build_ladder(d)
    ix = {q: i for i, q in enumerate(names)}
    for key, conds, side, am, flat in ladder:
        miss = [q for q in conds if q not in ix]
        if miss:
            if verbose:
                print(f"  {key}: SKIPPED, ladder has no {miss}")
            continue
        m = np.ones(len(c), bool)
        for q in conds:
            m &= M[ix[q]]
        out[key] = dict(mask=m, side=side, am=am, flat=flat)
    return d, out
