"""Features engineered FROM the Turtle's own components, for the 15-minute chart.

THE RULE THIS FILE OBEYS: no new indicator families. Every column below is derived from something
the strategy already computes -- the Donchian channels, ATR(20), ADX(14)/DI, EMA(100) -- or from
the geometry of the breakout itself. The brief's own test applies to each: it must answer a
specific question, and if the answer is no out of sample it goes.

CAUSALITY. Every feature is read at the SIGNAL bar and the trade fills at the next bar's open, so
a feature may use the signal bar's own OHLC. What it may never use is a rolling window that has not
closed: every percentile and every "previous failure" count is built from bars strictly before the
window ends. `audit()` recomputes the whole set on truncated history and requires an exact match.

PERCENTILES ARE EXPANDING, NOT FULL-SAMPLE. A percentile taken over the whole series tells a bar in
2023 where it ranks among bars from 2025. `_rank_pct` uses a trailing window only.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I  # noqa: E402


def _rank_pct(x, n=500):
    """Trailing percentile rank of x within its own last n values, inclusive of the current bar."""
    s = pd.Series(x)
    return s.rolling(n, min_periods=n // 4).apply(
        lambda w: (w[:-1] < w[-1]).mean(), raw=True).to_numpy()


def _slope(x, n):
    return (np.asarray(x, float) - I.shift(np.asarray(x, float), n)) / float(n)


def build(d, atr, C, e1=20, e2=55, adx_n=14, ema_n=100):
    """All engineered features, keyed by the question each one asks."""
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    n = len(c)
    F = {}
    hi1, hi2 = C["hi1"], C["hi2"]
    lo_e1 = I.shift(I.rmin(l, e1), 1)

    # ---- Donchian geometry: what separates a real breakout from a fake one? -------------------
    with np.errstate(invalid="ignore", divide="ignore"):
        F["brk_dist_atr"]   = (h - hi1) / atr            # how far through the channel we broke
        F["brk_close_atr"]  = (c - hi1) / atr            # ...measured at the CLOSE, not the high
        F["chan_width_atr"] = (hi1 - lo_e1) / atr        # is the channel wide or coiled?
        F["bar_size_atr"]   = (h - l) / atr              # breakout bar's own range
        F["close_in_bar"]   = np.where(h > l, (c - l) / (h - l), 0.5)   # did it close on its high?
    F["chan_width_pct"] = _rank_pct(F["chan_width_atr"])
    F["chan_expand"]    = F["chan_width_atr"] / np.maximum(I.shift(F["chan_width_atr"], 20), 1e-9)
    F["chan_compress"]  = I.shift(F["chan_width_atr"], 1) / np.maximum(
        pd.Series(F["chan_width_atr"]).rolling(50, min_periods=10).max().shift(1).to_numpy(), 1e-9)

    # bars spent inside the channel before this break, and consecutive closes outside it
    outside = np.nan_to_num(c > hi1, nan=0).astype(bool)
    inside_run = np.zeros(n); k = 0
    for i in range(n):
        k = 0 if outside[i] else k + 1
        inside_run[i] = k
    F["bars_inside"] = inside_run
    out_run = np.zeros(n); k = 0
    for i in range(n):
        k = k + 1 if outside[i] else 0
        out_run[i] = k
    F["closes_outside"] = out_run

    # PREVIOUS BREAKOUT FAILURES: a break that closed back inside within 5 bars. Counted over a
    # trailing 100 bars and shifted, so the current break never counts itself.
    brk = np.nan_to_num(h > hi1, nan=0).astype(bool)
    fail = np.zeros(n)
    for i in np.flatnonzero(brk):
        j = min(i + 5, n - 1)
        if j > i and np.any(c[i + 1:j + 1] < hi1[i]):
            fail[i] = 1.0
    F["fail_rate_100"] = I.shift(
        pd.Series(fail).rolling(100, min_periods=20).sum().to_numpy(), 1)
    F["brk_since"] = np.nan_to_num(
        I.shift(pd.Series(brk.astype(float)).rolling(50, min_periods=10).sum().to_numpy(), 1))

    # breakout velocity: how fast did price travel to get here, in ATR per bar
    F["velocity_5"]  = (c - I.shift(c, 5)) / (5.0 * np.maximum(atr, 1e-9))
    F["velocity_20"] = (c - I.shift(c, 20)) / (20.0 * np.maximum(atr, 1e-9))
    F["dist_hi2_atr"] = (hi2 - h) / np.maximum(atr, 1e-9)   # room to the 55-bar high

    # ---- ATR: does the regime the breakout happens in matter? ---------------------------------
    atr_l = pd.Series(atr).rolling(200, min_periods=50).mean().to_numpy()
    F["atr_pct"]    = _rank_pct(atr)
    F["atr_ratio"]  = atr / np.maximum(atr_l, 1e-9)
    F["atr_slope"]  = _slope(atr, 20) / np.maximum(atr, 1e-9)
    F["atr_expand"] = atr / np.maximum(I.shift(atr, 20), 1e-9)

    # ---- ADX and DI: where does a break have the best chance of continuing? -------------------
    adx, pdi, mdi = I.adx_di(h, l, c, adx_n)
    F["adx"]        = adx
    F["adx_slope"]  = _slope(adx, 5)
    F["adx_accel"]  = _slope(adx, 5) - I.shift(_slope(adx, 5), 5)
    F["adx_pct"]    = _rank_pct(adx)
    F["di_spread"]  = pdi - mdi
    F["di_ratio"]   = pdi / np.maximum(pdi + mdi, 1e-9)

    # ---- EMA100: is there a directional environment at all? -----------------------------------
    ema = I.ema(c, ema_n)
    with np.errstate(invalid="ignore", divide="ignore"):
        F["ema_dist_atr"] = (c - ema) / atr
    F["ema_dist_pct"] = _rank_pct(F["ema_dist_atr"])
    F["ema_slope"]    = _slope(ema, 20) / np.maximum(atr, 1e-9)
    F["ema_accel"]    = F["ema_slope"] - I.shift(F["ema_slope"], 20)
    F["above_ema"]    = (c > ema).astype(float)

    # ---- session context, the one non-Turtle input, because 15m bars are not interchangeable --
    F["mod"] = d["mod"].astype(float)
    return F


def audit(d, atr, C, checks=10, seed=5, verbose=True):
    """Recompute on history truncated at bar i and require an exact match at that bar."""
    rng = np.random.default_rng(seed)
    full = build(d, atr, C)
    n = len(d["c"])
    idx = rng.integers(int(0.6 * n), n - 1, checks)
    bad = []
    for i in idx:
        k = i + 1
        d2 = {kk: (vv[:k] if isinstance(vv, np.ndarray) else vv) for kk, vv in d.items()}
        d2["n"] = k
        C2 = {kk: vv[:k] for kk, vv in C.items()}
        f2 = build(d2, atr[:k], C2)
        for name in full:
            a, b = full[name][i], f2[name][i]
            if np.isfinite(a) != np.isfinite(b) or (np.isfinite(a) and abs(a - b) > 1e-9):
                bad.append((name, int(i), float(a), float(b)))
    if verbose:
        print(f"  truncation audit: {checks} bars x {len(full)} features = "
              f"{checks*len(full)} checks, {len(bad)} mismatches")
        for b in bad[:8]:
            print(f"    LEAK {b[0]} at {b[1]}: full {b[2]:+.6f} vs truncated {b[3]:+.6f}")
    return bad
