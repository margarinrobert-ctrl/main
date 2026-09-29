"""Candlestick pattern features on the Turtle's own signal bars, declared before anything is run.

THE PREDICTION, WRITTEN DOWN FIRST.  A breakout bar IS a candle shape: it made a new N-bar high, so
it closes in the upper part of its own range and has an above-average body.  Every BULLISH
continuation pattern is therefore a candidate for being the trigger restated -- this branch has
caught that eight times (RSI>=55 on 94.7% of breakout bars, Aroon osc>=0 on 100.0%, MACD>0 on
99.8-100.0%, MFI>=50 on 91.7%, EMA13>48 on 82.6%, +DI>-DI on 97.8%, close>EMA50 on 93.7%, C1 of the
VWAP-EMA spec at a coefficient of variation of exactly zero).  So the pool deliberately contains
BOTH polarities, and the ones with a prior are the REJECTION readings: a breakout bar that closes
back near its low, or leaves a long upper wick, is a failed break rather than a break.

EVERY FEATURE IS A COMPLETED-BAR READING.  Patterns use bars t, t-1, t-2 and nothing later, so they
are causal by construction -- which is exactly the claim `truncation_audit` exists to check rather
than assert (this branch has two real leaks that inspection missed).

CONTINUOUS FEATURES ARE CUT ON THE RESEARCH BLOCK AND THE NUMBER IS CARRIED UNCHANGED.  A whole
sample `np.nanquantile` reads the future -- `STUDY_V50_SELECTION` found it flipping 0.8-1.3% of bars
in a published family -- so the threshold is fitted once on research and used as a constant, which
is also what a script can actually do.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def _parts(o, h, l, c):
    rng = np.maximum(h - l, EPS)
    body = np.abs(c - o)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return rng, body, upper, lower


def build(d, atr):
    """Every declared candlestick feature at every bar.  Returns {name: float array}."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    rng, body, upper, lower = _parts(o, h, l, c)
    up = (c > o).astype(float)
    dn = (c < o).astype(float)

    def sh(a, k=1):
        out = np.full(n, np.nan)
        if k < n:
            out[k:] = a[:-k]
        return out

    o1, h1, l1, c1 = sh(o), sh(h), sh(l), sh(c)
    o2, h2, l2, c2 = sh(o, 2), sh(h, 2), sh(l, 2), sh(c, 2)
    rng1, body1, up1w, lo1w = _parts(o1, h1, l1, c1)
    rng2, body2, _, _ = _parts(o2, h2, l2, c2)
    body_med = pd.Series(body).rolling(50, min_periods=20).median().shift(1).to_numpy()
    rng_med = pd.Series(rng).rolling(50, min_periods=20).median().shift(1).to_numpy()
    atrs = np.where(atr > 0, atr, np.nan)

    F = {}

    # ---- shape: the continuous readings the patterns are built from -----------------------
    F["shp.body_share"] = body / rng
    F["shp.upper_share"] = upper / rng
    F["shp.lower_share"] = lower / rng
    F["shp.close_pos"] = (c - l) / rng
    F["shp.body_atr"] = body / atrs
    F["shp.range_atr"] = rng / atrs
    F["shp.range_vs_med"] = rng / np.where(rng_med > 0, rng_med, np.nan)
    F["shp.body_vs_med"] = body / np.where(body_med > 0, body_med, np.nan)
    F["shp.body_vs_prev"] = body / np.maximum(body1, EPS)
    F["shp.gap_atr"] = (o - c1) / atrs
    F["shp.close_vs_prev_hi"] = (c - h1) / atrs

    # ---- single-bar patterns ---------------------------------------------------------------
    small_body = body <= 0.10 * rng
    F["p1.doji"] = small_body.astype(float)
    F["p1.dragonfly"] = (small_body & (lower >= 0.60 * rng) & (upper <= 0.10 * rng)).astype(float)
    F["p1.gravestone"] = (small_body & (upper >= 0.60 * rng) & (lower <= 0.10 * rng)).astype(float)
    F["p1.long_leg_doji"] = (small_body & (upper >= 0.25 * rng) & (lower >= 0.25 * rng)).astype(float)
    F["p1.marubozu_bull"] = ((up > 0) & (body >= 0.90 * rng)).astype(float)
    F["p1.marubozu_bear"] = ((dn > 0) & (body >= 0.90 * rng)).astype(float)
    F["p1.hammer"] = ((body <= 0.35 * rng) & (lower >= 2.0 * body) & (upper <= 0.20 * rng)).astype(float)
    F["p1.inv_hammer"] = ((body <= 0.35 * rng) & (upper >= 2.0 * body) & (lower <= 0.20 * rng)).astype(float)
    F["p1.shooting_star"] = (((body <= 0.35 * rng) & (upper >= 2.0 * body) & (lower <= 0.20 * rng))
                             & (c1 < c)).astype(float)
    F["p1.spinning_top"] = ((body <= 0.30 * rng) & (upper >= 0.25 * rng)
                            & (lower >= 0.25 * rng)).astype(float)
    F["p1.belt_hold_bull"] = ((up > 0) & (lower <= 0.05 * rng) & (body >= 0.60 * rng)).astype(float)
    F["p1.closes_lower_third"] = ((c - l) / rng <= 1 / 3).astype(float)
    F["p1.long_upper_wick"] = (upper >= 0.50 * rng).astype(float)

    # ---- two-bar patterns ------------------------------------------------------------------
    F["p2.engulf_bull"] = ((up > 0) & (c1 < o1) & (c >= o1) & (o <= c1)).astype(float)
    F["p2.engulf_bear"] = ((dn > 0) & (c1 > o1) & (o >= c1) & (c <= o1)).astype(float)
    F["p2.harami_bull"] = ((up > 0) & (c1 < o1) & (h <= h1) & (l >= l1)).astype(float)
    F["p2.harami_bear"] = ((dn > 0) & (c1 > o1) & (h <= h1) & (l >= l1)).astype(float)
    F["p2.piercing"] = ((up > 0) & (c1 < o1) & (o < l1) & (c > (o1 + c1) / 2) & (c < o1)).astype(float)
    F["p2.dark_cloud"] = ((dn > 0) & (c1 > o1) & (o > h1) & (c < (o1 + c1) / 2) & (c > o1)).astype(float)
    F["p2.tweezer_top"] = (np.abs(h - h1) <= 0.05 * np.maximum(atrs, EPS)).astype(float)
    F["p2.tweezer_bottom"] = (np.abs(l - l1) <= 0.05 * np.maximum(atrs, EPS)).astype(float)
    F["p2.inside_bar"] = ((h <= h1) & (l >= l1)).astype(float)
    F["p2.outside_bar"] = ((h > h1) & (l < l1)).astype(float)
    F["p2.gap_up"] = (o > h1).astype(float)
    F["p2.gap_dn"] = (o < l1).astype(float)
    F["p2.kicker_bull"] = ((up > 0) & (c1 < o1) & (o > o1)).astype(float)
    F["p2.prev_upper_wick"] = (up1w / rng1 >= 0.50).astype(float)

    # ---- three-bar patterns ----------------------------------------------------------------
    F["p3.morning_star"] = ((c2 < o2) & (np.abs(c1 - o1) <= 0.30 * rng1)
                            & (up > 0) & (c > (o2 + c2) / 2)).astype(float)
    F["p3.evening_star"] = ((c2 > o2) & (np.abs(c1 - o1) <= 0.30 * rng1)
                            & (dn > 0) & (c < (o2 + c2) / 2)).astype(float)
    F["p3.three_white"] = ((up > 0) & (c1 > o1) & (c2 > o2) & (c > c1) & (c1 > c2)
                           & (body >= 0.5 * rng) & (body1 >= 0.5 * rng1)
                           & (body2 >= 0.5 * rng2)).astype(float)
    F["p3.three_black"] = ((dn > 0) & (c1 < o1) & (c2 < o2) & (c < c1) & (c1 < c2)).astype(float)
    F["p3.three_inside_up"] = ((c2 < o2) & (c1 > o1) & (h1 <= h2) & (l1 >= l2)
                               & (up > 0) & (c > c1)).astype(float)

    # ---- sequence --------------------------------------------------------------------------
    upc = (c > c1).astype(float)
    F["seq.up_closes_3"] = (pd.Series(upc).rolling(3).sum().to_numpy() == 3).astype(float)
    F["seq.up_closes_5"] = pd.Series(upc).rolling(5).sum().to_numpy()
    hh = (h > h1).astype(float)
    F["seq.higher_highs_3"] = (pd.Series(hh).rolling(3).sum().to_numpy() == 3).astype(float)
    F["seq.bull_share_10"] = pd.Series(up).rolling(10).mean().to_numpy()
    F["seq.wick_rej_5"] = pd.Series((upper >= 0.5 * rng).astype(float)).rolling(5).sum().to_numpy()
    return F


NAMES = None


def truncation_audit(d, atr, probes=20, seed=0):
    """Recompute every feature on history that ENDS at bar i and require the value to match.

    The only honest leakage test on this branch: it caught overnight aggregates reading their own
    group's last close, and a divergence feature that knew when a FUTURE pivot would confirm."""
    full = build(d, atr)
    rng = np.random.default_rng(seed)
    n = len(d["c"])
    idx = rng.choice(np.arange(300, n), size=min(probes, n - 300), replace=False)
    bad = []
    for i in sorted(idx):
        cut = {k: v[:i + 1] for k, v in d.items() if isinstance(v, np.ndarray)}
        ft = build(cut, atr[:i + 1])
        for k in full:
            a, b = full[k][i], ft[k][i]
            if np.isfinite(a) != np.isfinite(b) or (np.isfinite(a) and abs(a - b) > 1e-9):
                bad.append((k, int(i), float(a), float(b)))
    return bad, len(idx) * len(full)
