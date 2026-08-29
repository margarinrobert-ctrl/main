"""V39 -- a Monte Carlo mean for EVERY individual indicator rule, and for the best versions.

WHAT IS ASKED AND WHAT IS ANSWERED. "The Monte Carlo mean" of a rule is ambiguous in a way that
decides the result, so both are reported and kept apart (`CLAUDE.md`: permuting trades cannot
change the endpoint):

  BOOTSTRAP MEAN   resample whole DAYS WITH THEIR TRADES ATTACHED, 1,000 draws, take the
                   trade-weighted mean each time. This is the EDGE question -- what $/trade is,
                   with an interval, and P(mean <= 0). Days, not trades, because triggers cluster:
                   260 trades here are ~100 independent days.
  PERMUTATION      reorder the realised trades 1,000 times and read the DRAWDOWN distribution.
                   This is the PATH question. Its endpoint is invariant by construction and is
                   never reported.

EVERY RULE IS ALSO SCORED AGAINST A SAME-SELECTIVITY CONTROL -- a random filter keeping the same
number of breakout signals from the same pool through the same position lock. A restrictive filter
raises profit factor by restrictiveness alone (`CLAUDE.md` records an ATR filter that went PF
1.42 -> 1.77 and was indistinguishable from noise), so a bootstrap interval that excludes zero is
NOT evidence that the indicator did anything. The control column is what answers that.

THE BASE is the branch's shipped geometry: Donchian 30 entry, 20-bar channel exit, 2.0 x ATR(14)
stop, NO take profit, one unit, long, market order at the next open. Each indicator is added to it
ALONE -- this is a table of individual rules, not a search over stacks.

THREE MARKETS. NQ (which chose this geometry), and US30 and US100, which did not.

Usage: python3 research/v39/v39mc.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v20")
sys.path.insert(0, "research/v38")
import indicators as I       # noqa: E402
import fastbars as FB        # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
from v20linreg import linreg  # noqa: E402

BASE = dict(entry_n=30, exit_n=20, stop_n=2.0, tp_r=0.0)
DRAWS = 1000
CTRL = 400


def chop(h, l, c, n=14):
    tr = I.true_range(h, l, c)
    return (100 * np.log10(I.rsum(tr, n) / np.maximum(I.rmax(h, n) - I.rmin(l, n), 1e-9))
            / np.log10(n))


def rank(x, n):
    """Percentile of x within its own trailing n bars, causal."""
    s = pd.Series(x)
    return s.rolling(n).apply(lambda w: float((w[:-1] <= w[-1]).mean()), raw=True).to_numpy()


def rules(P):
    """Every individual indicator condition, each a boolean array. Causal by construction."""
    h, l, c, v = P["h"], P["l"], P["c"], P.get("v")
    atr = P["atr"]
    R = {}
    ch = chop(h, l, c, 14)
    for t in (35, 40, 45, 50):
        R[f"CHOP14 <= {t}"] = ch <= t
    adx, pdi, mdi = I.adx_di(h, l, c, 14)
    for t in (20, 25, 30):
        R[f"ADX14 >= {t}"] = adx >= t
    R["+DI > -DI"] = pdi > mdi
    rs = I.rsi(c, 14)
    for t in (50, 55, 60):
        R[f"RSI14 >= {t}"] = rs >= t
    for n in (9, 21, 50):
        vf, sf, r2 = linreg(c, n)
        R[f"close > linreg({n})"] = c > vf
        R[f"linreg({n}) slope > 0"] = sf > 0
    v9, s9, _ = linreg(c, 9)
    v21, s21, _ = linreg(c, 21)
    R["linreg 9/21 value state"] = v9 > v21
    R["linreg 9/21 slope state"] = s9 > s21
    for n in (50, 100, 200):
        R[f"close > SMA{n}"] = c > I.sma(c, n)
        R[f"close > EMA{n}"] = c > I.ema(c, n)
    R["EMA50 > EMA200"] = I.ema(c, 50) > I.ema(c, 200)
    er = np.abs(c - I.shift(c, 20)) / np.maximum(I.rsum(np.abs(np.diff(c, prepend=c[0])), 20), 1e-9)
    for t in (0.2, 0.3):
        R[f"efficiency ratio(20) >= {t}"] = er >= t
    am = I.sma(atr, 20)
    R["ATR expanding (>= 1.10x mean)"] = atr >= 1.10 * am
    R["ATR contracting (<= 0.90x mean)"] = atr <= 0.90 * am
    vp = rank(atr, 250)
    R["vol percentile <= 0.5 (calm)"] = vp <= 0.5
    R["vol percentile > 0.5 (fast)"] = vp > 0.5
    R["ATR pct rank(500) <= 0.2"] = rank(atr, 500) <= 0.2
    bup, _bmid, blo, _bw = I.bollinger(c, 20, 2.0)   # returns (upper, mid, lower, width)
    R["close > Bollinger upper(20,2)"] = c > bup
    R["BB width > its 20-bar mean"] = (bup - blo) > I.sma(bup - blo, 20)
    _ml, _ms = I.macd(c)                              # returns (line, signal), no histogram
    R["MACD histogram > 0"] = (_ml - _ms) > 0
    R["close > prior 55-bar high"] = c > I.shift(I.rmax(h, 55), 1)
    R["body >= 60% of range"] = np.abs(c - P["o"]) >= 0.6 * np.maximum(h - l, 1e-9)
    R["body <= 30% of range"] = np.abs(c - P["o"]) <= 0.3 * np.maximum(h - l, 1e-9)
    if v is not None:
        R["volume > 1.5x its 20-bar mean"] = v > 1.5 * I.sma(v, 20)
    return R


def boot(pnl, day, draws=DRAWS, seed=11):
    rng = np.random.default_rng(seed)
    days = np.unique(day)
    grp = [pnl[day == u] for u in days]
    m = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, len(grp), len(grp))
        m[i] = np.concatenate([grp[j] for j in pick]).mean()
    return dict(mc_mean=float(m.mean()), p5=float(np.percentile(m, 5)),
                p50=float(np.percentile(m, 50)), p95=float(np.percentile(m, 95)),
                p_le0=float((m <= 0).mean()))


def perm(pnl, draws=DRAWS, seed=13):
    rng = np.random.default_rng(seed)
    dd = np.empty(draws)
    for i in range(draws):
        eq = np.cumsum(rng.permutation(pnl))
        dd[i] = np.max(np.maximum.accumulate(eq) - eq)
    eq = np.cumsum(pnl)
    return dict(dd_real=float(np.max(np.maximum.accumulate(eq) - eq)),
                dd50=float(np.percentile(dd, 50)), dd95=float(np.percentile(dd, 95)),
                dd99=float(np.percentile(dd, 99)))


def gather(P, xb, pnl, sig):
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    k = G._lock(sig, xb, pnl, bp, bs)
    return bp[:k].copy(), bs[:k].copy()


def control(P, xb, pnl, pool, n_keep, draws=CTRL, seed=29):
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    for i in range(draws):
        pick = np.sort(rng.choice(pool, size=min(n_keep, len(pool)), replace=False))
        p, _s = gather(P, xb, pnl, pick)
        out[i] = p.mean() if len(p) else np.nan
    return out[np.isfinite(out)]
