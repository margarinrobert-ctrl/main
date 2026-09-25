"""V44 -- a declared causal feature pool, scored by the excursions it produces.

THE BRIEF: engineer features, take the four with the highest mean MFE and the four with the lowest
mean MAE, and build a 5m/15m scalping strategy in 07:00-11:00 New York with a target and a stop.

THE TRAP THAT IS BUILT INTO THAT SELECTION RULE, stated before any result: MFE and MAE are both
monotone in realised volatility over the horizon. A feature that predicts a fast next hour raises
BOTH; one that predicts a calm next hour lowers both. So "highest MFE" is a bet on volatility and
"lowest MAE" is a bet against it, and the two lists are at risk of being opposites rather than
complements. `v44run.py` measures the rank correlation between the two criteria across the pool
instead of assuming it either way, and reports the RATIO MFE/MAE, which is the only one of the
three that is not a volatility reading.

Excursions are in ATR AT THE SIGNAL BAR over a FIXED HORIZON with no barriers -- STUDY_V43's
correction. Dividing by R would put the stop back in the denominator, and letting a stop bind would
censor the adverse side at the stop distance.

EVERY FEATURE IS CAUSAL AND IS PROVED SO. `audit()` recomputes each column on history TRUNCATED at
bar i and requires the value to match what the full-history computation put there. That test has
caught two real leaks on this branch that inspection missed.

NO CALENDAR CONDITIONS. Weekday and month partition the sample and hand a search a free lottery;
they are banned from rule search here. Time-of-day is excluded on the same principle -- the session
window is a stated constraint of the brief, not something the search may optimise.

Usage: imported by v44run.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
import indicators as I       # noqa: E402

SPLIT = 0.65


def _safe(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.isfinite(b) & (b != 0), a / b, np.nan)


def build(o, h, l, c, v):
    """36 declared causal features in 6 concept families. Every one reads bars up to and
    including the current CLOSE and nothing after it."""
    f = {}
    tr = I.true_range(h, l, c)
    atr = I.rma(tr, 14)
    rng = h - l

    # --- 1. TREND / MOMENTUM -------------------------------------------------------------------
    adx, dip, dim = I.adx_di(h, l, c, 14)
    f["mom.rsi14"] = I.rsi(c, 14)
    f["mom.rsi7"] = I.rsi(c, 7)
    f["mom.roc10"] = I.roc(c, 10)
    f["mom.roc30"] = I.roc(c, 30)
    macd_l, macd_s = I.macd(c, 12, 26, 9)
    f["mom.macd_hist"] = _safe(macd_l - macd_s, atr)
    f["mom.di_spread"] = dip - dim
    f["mom.adx14"] = adx
    f["mom.slope20"] = _safe(I.lin_slope(c, 20), atr)

    # --- 2. VOLATILITY LEVEL AND CHANGE --------------------------------------------------------
    atr50 = I.rma(tr, 50)
    f["vol.atr_ratio"] = _safe(atr, atr50)
    f["vol.range_atr"] = _safe(rng, atr)
    f["vol.rstd20_atr"] = _safe(I.rstd(c, 20), atr)
    bb_u, _bb_m, bb_l, bb_w = I.bollinger(c, 20, 2.0)
    f["vol.bb_width"] = _safe(bb_w, atr)
    f["vol.atr_pct250"] = pd.Series(atr).rolling(250, min_periods=50).rank(pct=True).to_numpy()
    f["vol.range_exp"] = _safe(I.rsum(tr, 5), 5.0 * atr50)

    # --- 3. CHOP / EFFICIENCY ------------------------------------------------------------------
    n = 14
    span = I.rmax(h, n) - I.rmin(l, n)
    f["chp.chop14"] = 100.0 * np.log10(np.maximum(_safe(I.rsum(tr, n), span), 1e-12)) / np.log10(n)
    f["chp.er20"] = _safe(np.abs(c - I.shift(c, 20)), I.rsum(np.abs(np.diff(c, prepend=c[0])), 20))
    f["chp.er10"] = _safe(np.abs(c - I.shift(c, 10)), I.rsum(np.abs(np.diff(c, prepend=c[0])), 10))
    f["chp.dir_persist"] = I.rsum(np.sign(np.diff(c, prepend=c[0])), 10)

    # --- 4. LOCATION -- where price sits, in ATR ------------------------------------------------
    for p in (20, 50, 200):
        f[f"loc.d_ema{p}"] = _safe(c - I.ema(c, p), atr)
    f["loc.don_pos20"] = _safe(c - I.rmin(l, 20), I.rmax(h, 20) - I.rmin(l, 20))
    f["loc.don_pos50"] = _safe(c - I.rmin(l, 50), I.rmax(h, 50) - I.rmin(l, 50))
    f["loc.bb_pos"] = _safe(c - bb_l, bb_u - bb_l)
    f["loc.d_hi20"] = _safe(I.rmax(h, 20) - c, atr)
    f["loc.d_lo20"] = _safe(c - I.rmin(l, 20), atr)

    # --- 5. BAR SHAPE --------------------------------------------------------------------------
    f["bar.close_pos"] = _safe(c - l, rng)
    f["bar.body_frac"] = _safe(np.abs(c - o), rng)
    f["bar.upper_wick"] = _safe(h - np.maximum(o, c), rng)
    f["bar.lower_wick"] = _safe(np.minimum(o, c) - l, rng)
    f["bar.gap_atr"] = _safe(o - I.shift(c, 1), atr)
    f["bar.ret1_atr"] = _safe(c - I.shift(c, 1), atr)
    f["bar.ret3_atr"] = _safe(c - I.shift(c, 3), atr)

    # --- 6. PARTICIPATION ----------------------------------------------------------------------
    vs = pd.Series(np.asarray(v, float))
    f["vlm.rel20"] = _safe(vs.to_numpy(), vs.rolling(20, min_periods=5).mean().to_numpy())
    f["vlm.rel100"] = _safe(vs.to_numpy(), vs.rolling(100, min_periods=20).mean().to_numpy())
    f["vlm.trend"] = _safe(vs.rolling(5, min_periods=2).mean().to_numpy(),
                           vs.rolling(50, min_periods=10).mean().to_numpy())
    f["vlm.effort"] = _safe(np.abs(c - I.shift(c, 1)), atr) * _safe(
        vs.rolling(20, min_periods=5).mean().to_numpy(), vs.to_numpy())
    f["vlm.obv_slope"] = _safe(I.lin_slope(I.obv(c, np.asarray(v, float)), 20),
                               vs.rolling(20, min_periods=5).mean().to_numpy())
    f["vlm.mfi14"] = I.mfi(h, l, c, np.asarray(v, float), 14)

    return f, atr


FAMILIES = ("mom", "vol", "chp", "loc", "bar", "vlm")


def audit(o, h, l, c, v, probes=(3000, 5000, 8000, 11000), tol=1e-8):
    """Truncation audit: recompute on history ENDING at bar i and require the value to match.

    A feature that reads even one bar into the future changes when the series is cut there. This
    is the only honest leakage test -- inspection has missed two real leaks on this branch."""
    full, _ = build(o, h, l, c, v)
    bad = {}
    for i in probes:
        if i >= len(c):
            continue
        cut, _ = build(o[:i + 1], h[:i + 1], l[:i + 1], c[:i + 1], v[:i + 1])
        for k in full:
            a, b = full[k][i], cut[k][i]
            if np.isnan(a) and np.isnan(b):
                continue
            if not np.isfinite(a) or not np.isfinite(b) or abs(a - b) > tol * max(1.0, abs(a)):
                bad.setdefault(k, []).append(i)
    return bad
