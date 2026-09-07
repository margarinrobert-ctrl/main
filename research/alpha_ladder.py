"""An expanded condition pool: the same features, at more than one threshold.

`alpha_factory2.build_conditions` fixes every threshold at one value -- ATR above 1.5x its mean,
Bollinger width below 0.7x its mean, close below the 20-bar low. Those numbers were chosen for
readability, not measured, and a rule that needs 1.3x is invisible to a search that can only ask
for 1.5x. Worse for the question actually being asked here: a rule fixed at the tight end of
every threshold cannot produce many trades no matter which conditions are combined.

So each continuous feature gets a LADDER of thresholds instead of a single rung. 115 conditions
become 190, and three-way combinations go from 253,575 to 1,147,205.

Two things this deliberately does NOT do:

  * no new features. Every rung here is a threshold on something `build_conditions` already
    computes. This is a finer grid over the same space, not a wider space, and that matters for
    how much the multiplicity is worth worrying about.
  * no new calendar conditions. Weekday and month are banned outright (CLAUDE.md); the five
    existing clock windows are carried through unchanged and no finer ones are added, because a
    finer clock grid is exactly the free lottery the ban exists to prevent.

Every rung carries its Pine expression next to its numpy definition, so the two cannot drift.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from alpha_factory2 import build_conditions

# name -> Pine boolean expression, for the rungs this module adds. Filled at import (see the
# bottom of the file) so importers get a complete map without touching price data.
PINE = {}


def _add(S, name, series, pine):
    """`series` is a thunk, so the Pine map can be built without any price data.

    `oner_more_pine` imports PINE at module load and would otherwise get an empty dict, because
    nothing had called this function yet -- which is exactly what happened: three of the four
    scripts emitted and the fourth reported a missing expression for a rung that plainly exists.
    """
    if name in S:                     # already a rung in build_conditions -- keep the original
        return
    S[name] = series
    PINE[name] = pine


def ladder_conditions(d=None):
    """Threshold rungs on features build_conditions already has.

    With `d`, returns {name: bool array}. With d=None, evaluates nothing and only fills PINE."""
    if d is None:
        # a short synthetic series: every rung still gets built and registered, and the arrays
        # are thrown away. Cheaper and far less error-prone than a second copy of the loops.
        rng = np.random.default_rng(0)
        c_ = 100 + np.cumsum(rng.normal(0, 1, 400))
        d = dict(o=c_, h=c_ + 1, l=c_ - 1, c=c_, v=np.full(400, 1000.0),
                 atr=np.full(400, 2.0))
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    atr_ = d["atr"]
    S = {}

    # ---- volatility level: ATR against its own 20-bar mean ------------------------------------
    a20 = I.sma(atr_, 20)
    for k in (1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0):
        _add(S, f"ATR>{k}x mean", atr_ > k * a20, f"atrV > {k} * atrMean20")
    for k in (0.6, 0.7, 0.8, 0.9):
        _add(S, f"ATR<{k}x mean", atr_ < k * a20, f"atrV < {k} * atrMean20")

    # ---- Bollinger width against its own 50-bar mean -------------------------------------------
    _bu, _bm, _bl, bw = I.bollinger(c)
    bwm = I.sma(bw, 50)
    for k in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        _add(S, f"BB width<{k}x mean", bw < k * bwm, f"bbWidth < {k} * ta.sma(bbWidth, 50)")
    for k in (1.2, 1.5):
        _add(S, f"BB width>{k}x mean", bw > k * bwm, f"bbWidth > {k} * ta.sma(bbWidth, 50)")

    # ---- range extremes: how far back the broken level is --------------------------------------
    for n in (3, 5, 8, 10, 15, 20, 30, 50, 75, 100):
        _add(S, f"close>{n}-bar high", c > I.shift(I.rmax(h, n)),
             f"close > ta.highest(high, {n})[1]")
        _add(S, f"close<{n}-bar low", c < I.shift(I.rmin(l, n)),
             f"close < ta.lowest(low, {n})[1]")

    # ---- oscillator rungs ----------------------------------------------------------------------
    r14 = I.rsi(c, 14)
    for k in (20, 25, 35, 40):
        _add(S, f"RSI14<{k}", r14 < k, f"rsi14 < {k}")
    for k in (60, 65, 75, 80):
        _add(S, f"RSI14>{k}", r14 > k, f"rsi14 > {k}")
    kk, _dd = I.stoch(h, l, c)
    for k in (10, 15, 25, 30, 35):
        _add(S, f"Stoch K<{k}", kk < k, f"stK < {k}")
    for k in (65, 70, 85, 90):
        _add(S, f"Stoch K>{k}", kk > k, f"stK > {k}")
    ad, _p, _m = I.adx_di(h, l, c)
    for k in (15, 35):
        _add(S, f"ADX>{k}", ad > k, f"adx14 > {k}")

    # ---- bar shape ------------------------------------------------------------------------------
    rg = np.maximum(h - l, 1e-12)
    body = np.abs(c - o) / rg
    for k in (0.5, 0.75):
        _add(S, f"body>{int(100*k)}%", body > k, f"bodyFrac > {k}")
    for k in (0.15, 0.2):
        _add(S, f"body<{int(100*k)}%", body < k, f"bodyFrac < {k}")
    lw = (np.minimum(c, o) - l) / rg
    uw = (h - np.maximum(c, o)) / rg
    for k in (0.3, 0.35, 0.4, 0.6, 0.65):
        _add(S, f"lower wick>{int(100*k)}%", lw > k,
             f"(math.min(close, open) - low) / barRange > {k}")
        _add(S, f"upper wick>{int(100*k)}%", uw > k,
             f"(high - math.max(close, open)) / barRange > {k}")

    # ---- bar range against ATR -------------------------------------------------------------------
    r_atr = (h - l) / np.maximum(atr_, 1e-12)
    for k in (1.2, 2.0, 2.5):
        _add(S, f"range>{k}xATR", r_atr > k, f"(high - low) > {k} * atrV")
    for k in (0.3, 0.7):
        _add(S, f"range<{k}xATR", r_atr < k, f"(high - low) < {k} * atrV")

    # ---- volume ------------------------------------------------------------------------------------
    vm = I.sma(v, 20)
    for k in (1.2, 3.0):
        _add(S, f"vol>{k}x mean", v > k * vm, f"volume > {k} * volMean20")
    for k in (0.6, 0.9):
        _add(S, f"vol<{k}x mean", v < k * vm, f"volume < {k} * volMean20")

    # ---- distance from the 200 EMA, in ATRs --------------------------------------------------------
    e200 = I.ema(c, 200)
    dist = np.abs(c - e200) / np.maximum(atr_, 1e-12)
    for k in (0.5, 1.5, 3.0):
        _add(S, f"dist EMA200>{k} ATR", dist > k, f"math.abs(close - ema200) / atrV > {k}")
    for k in (0.25, 0.75):
        _add(S, f"dist EMA200<{k} ATR", dist < k, f"math.abs(close - ema200) / atrV < {k}")

    # ---- Donchian rungs ------------------------------------------------------------------------------
    for n in (10, 50):
        _add(S, f"close>Donchian{n} high", c > I.shift(I.rmax(h, n)),
             f"close > ta.highest(high, {n})[1]")
        _add(S, f"close<Donchian{n} low", c < I.shift(I.rmin(l, n)),
             f"close < ta.lowest(low, {n})[1]")

    # ---- momentum over more horizons -----------------------------------------------------------------
    for n in (3, 10, 50):
        _add(S, f"{n}-bar momentum>0", c > I.shift(c, n), f"close > close[{n}]")

    return S


def build_ladder(d):
    """The 115 original conditions, then every rung this module adds. Names stay unique."""
    names, M = build_conditions(d)
    have = set(names)
    S = {k: vv for k, vv in ladder_conditions(d).items() if k not in have}
    if not S:
        return names, M
    n = M.shape[1]
    extra = np.zeros((len(S), n), np.bool_)
    for i, k in enumerate(S):
        x = np.nan_to_num(np.asarray(S[k], dtype=float), nan=0.0)
        extra[i] = x > 0.5
    extra[:, :300] = False
    return names + list(S), np.vstack([M, extra])


if __name__ == "__main__":
    from bos_choch import prep
    from itertools import combinations as _cmb
    d = prep(30)
    base, _ = build_conditions(d)
    names, M = build_ladder(d)
    n = len(names)
    rules = n + len(list(_cmb(range(n), 2))) + len(list(_cmb(range(n), 3)))
    print(f"{len(base)} original conditions + {n - len(base)} new rungs = {n}")
    print(f"rules of up to three conditions: {rules:,}")
    print(f"x 36 geometries x 3 timeframes  = {rules * 36 * 3:,} combinations")
    miss = [k for k in names[len(base):] if k not in PINE]
    print(f"new rungs without a Pine expression: {len(miss)} {miss[:5]}")
    fire = M.mean(1)
    print(f"\nhit rate of the new rungs: min {fire[len(base):].min():.4f}  "
          f"median {np.median(fire[len(base):]):.4f}  max {fire[len(base):].max():.4f}")


ladder_conditions()          # populate PINE at import; the arrays it builds are discarded
