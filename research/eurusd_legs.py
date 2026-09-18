"""The six 30-minute shipped legs, run unchanged on EURUSD.

WHY THIS IS THE CLEANEST OUT-OF-SAMPLE TEST AVAILABLE HERE. Every previous cross-instrument check
on this branch carried an objection. US100 over the overlapping calendar was 68% THE SAME TRADES
(`STUDY_TREND_LONG.md`). US100 before 2022-12-26 was a genuine test but the same underlying index.
EURUSD is a different ASSET CLASS over a period that shares NOT ONE BAR with the NQ file -- it ends
2022-02-22 and NQ starts 2022-12-26 -- and it is 18.6 years against NQ's three.

WHAT IS AND IS NOT HELD FIXED. The rules and geometry are UNCHANGED: same conditions, same side,
same ATR stop multiple, same 1R target, same flatten time. Nothing is refitted, and no parameter is
searched here -- if a leg fails, it fails.

Two things necessarily change, and both are stated rather than hidden. The clock conditions ("first
120 minutes", "flat at 15:00") are New York equity-session windows applied to a market with no
equity session; they still land on the London/New York overlap, which is EURUSD's own busiest
period, but they were not chosen for it. And COSTS come from the feed's MEASURED spread rather than
an assumption -- this is the first test on the branch that can do that.

SCORING IS IN R UNITS, never dollars: EURUSD trades at 1.1 and NQ at 20,000, and dollar figures
would not be comparable. Each leg is scored against a MINUTE-OF-DAY MATCHED CONTROL -- random
entries with the same side, geometry and time-of-day distribution -- because that is the null that
prices drift, costs, barrier width and session timing at once. Benjamini-Hochberg at 0.10 across
the six.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
from edgelab import fx

TP_R = 1.0
MAX_HOLD = 200          # bars; the flatten time binds long before this


def eur_bars(atr_n=14):
    """EURUSD 30m in the dict shape the research pools expect, plus the measured spread."""
    b = fx.bars("EURUSD", 30, atr_n=atr_n)
    d = dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"], atr=b["atr"],
             mod=b["mod"].astype(np.int64), spread=b["spread"], idx=b["idx"])
    d["sess"] = ((b["idx"] + pd.Timedelta(hours=6)).normalize().view("int64")
                 // 86_400_000_000_000)
    d["df"] = b["df"]          # the factory pool reads `df.index` for its calendar conditions
    d["n"] = len(b["c"])
    return d


@njit(cache=True)
def _walk(o, h, l, c, atr, mod, spread, trig, side, am, flat, tp_r, max_hold, slip_mult):
    """Barrier walk in R units. Entry at the next open; stop wins a tied bar; flat at `flat`."""
    n = len(c); m = len(trig)
    R = np.zeros(m); why = np.zeros(m, np.int64); held = np.zeros(m, np.int64)
    k = 0
    for t in range(m):
        i = trig[t]
        if i + 1 >= n or atr[i] <= 0.0:
            continue
        e = i + 1
        hs = spread[e] * 0.5
        entry = o[e] + side * hs
        risk = am * atr[i]
        stop = entry - side * risk
        target = entry + side * tp_r * risk
        j = e
        r = 0.0; w = 4
        while j < n and (j - e) < max_hold:
            hit = (l[j] <= stop) if side == 1 else (h[j] >= stop)
            won = (h[j] >= target) if side == 1 else (l[j] <= target)
            if hit:
                px = stop - side * (spread[j] * 0.5 * slip_mult)
                r = side * (px - entry) / risk; w = 1
                break
            if won:
                px = target - side * spread[j] * 0.5
                r = side * (px - entry) / risk; w = 2
                break
            if flat > 0 and mod[j] >= flat:
                px = c[j] - side * spread[j] * 0.5
                r = side * (px - entry) / risk; w = 3
                break
            j += 1
        if w == 4:
            jj = j if j < n else n - 1
            r = side * (c[jj] - side * spread[jj] * 0.5 - entry) / risk
        R[k] = r; why[k] = w; held[k] = j - e; k += 1
    return R[:k], why[:k], held[:k]


def run(d, mask, side, am, flat, slip_mult=1.0):
    m = np.asarray(mask).copy(); m[:300] = False
    trig = np.flatnonzero(m & np.isfinite(d["atr"]) & (d["atr"] > 0)).astype(np.int64)
    R, why, held = _walk(d["o"], d["h"], d["l"], d["c"], d["atr"], d["mod"], d["spread"],
                         trig, side, am, flat, TP_R, MAX_HOLD, slip_mult)
    return trig, R, why, held


def control(d, trig, side, am, flat, draws=400, seed=11, slip_mult=1.0):
    """Minute-of-day matched random entries: same side, geometry and clock, no rule."""
    mod = d["mod"]
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
    for s in range(draws):
        pick = []
        for k, cnt in want.items():
            p = pools.get(k)
            if p is None or not len(p):
                continue
            pick.append(rng.choice(p, size=cnt, replace=True))
        if not pick:
            out[s] = np.nan; continue
        tt = np.sort(np.concatenate(pick)).astype(np.int64)
        R, _w, _h = _walk(d["o"], d["h"], d["l"], d["c"], d["atr"], d["mod"], d["spread"],
                          tt, side, am, flat, TP_R, MAX_HOLD, slip_mult)
        out[s] = R.mean() if len(R) else np.nan
    return out[np.isfinite(out)]


def bh(pvals, q=0.10):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    n = len(p)
    keep = np.zeros(n, bool)
    for rank, idx in enumerate(order, start=1):
        if p[idx] <= q * rank / n:
            keep[order[:rank]] = True
    return keep


# --------------------------------------------------------------- the six legs
# Rules reproduced from `allstrats.all_strategies()` at the thresholds actually shipped. V1 and V2
# go through their own FAMILIES function; V2L is V2's exact mirror; the three M legs are looked up
# in the ladder pool built on EURUSD, which is how they are defined on NQ too.
def leg_masks(d, verbose=True):
    import indicators as I
    from oner_union import FAMILIES
    from alpha_ladder import build_ladder

    out = {}
    out["V1"] = dict(mask=FAMILIES["V1"]["fn"](d, 1.2, 0.7, 5), side=1, am=3.0, flat=900,
                     rule="ATR>1.2x mean AND BB width<0.7x mean AND close<5-bar low")
    out["V2"] = dict(mask=FAMILIES["V2"]["fn"](d, (20, 50), 0.2, 120), side=-1, am=1.0, flat=960,
                     rule="EMA20>EMA50 AND bear engulf b>=0.2 AND first 120m")

    o, h, l, c, mod = d["o"], d["h"], d["l"], d["c"], d["mod"]
    body = np.abs(c - o) / np.maximum(h - l, 1e-12)
    bull = (c > I.shift(o)) & (o < I.shift(c)) & (c > o) & (body >= 0.2)
    out["V2L"] = dict(mask=(I.ema(c, 20) < I.ema(c, 50)) & bull & (mod >= 570) & (mod < 690),
                      side=1, am=2.5, flat=900,
                      rule="EMA20<EMA50 AND bull engulf b>=0.2 AND first 120m")

    names, M = build_ladder(d)
    ix = {q: i for i, q in enumerate(names)}
    for key, conds, side, am, flat in (
            ("M1", ("ATR>1.2x mean", "bullish engulfing", "upper wick>60%"), 1, 1.0, 900),
            ("M2", ("EMA20>EMA50", "bearish engulfing", "first hour"), -1, 1.0, 900),
            ("M4", ("body<30%", "first hour", "ATR>1.8x mean"), 1, 4.0, 960)):
        miss = [q for q in conds if q not in ix]
        if miss:
            if verbose:
                print(f"  {key}: SKIPPED, ladder has no {miss}")
            continue
        m = np.ones(len(c), bool)
        for q in conds:
            m &= M[ix[q]]
        out[key] = dict(mask=m, side=side, am=am, flat=flat, rule=" AND ".join(conds))
    return out
