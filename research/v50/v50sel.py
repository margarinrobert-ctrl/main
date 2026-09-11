"""V50 -- SELECTION at a FIXED FILL RATE. The follow-up V49's own post-mortem generated.

WHY THIS QUANTITY AND NOT V49's. V49 tested (limit - market), which decomposed into two forces of
about 0.54 R each that cancel to -0.013 in 44 of 44 families: SELECTION (which signals a resting
limit ends up filling) and PRICE (the better fill, close to the arithmetic identity 1.0 ATR entry
divided by a 2.0 ATR risk = 0.5 R). The hypothesised gradient was measurably STRONGER against
SELECTION (rho -0.384) than against the net (-0.321). So the mechanism was named correctly and the
wrong quantity was tested. This tests SELECTION directly.

WHY THE FILL RATE IS HELD CONSTANT. SELECTION = mean market R over the filled subset minus the mean
over all signals. Algebraically SELECTION = (1 - phi) * (mu_fill - mu_nofill), so it scales with the
NON-fill rate: two families with the same underlying adverse selection but different fill rates
report different SELECTION. V49 left the fill rate to fall out of a declared 5-minute expiry and got
17.3%. Here the expiry is swept PER FAMILY to put every family's fill rate in the same narrow band,
and the phi-invariant gap (mu_fill - mu_nofill) is reported beside it as the algebraic cross-check.

WHY BOTH SIDES. V49's immediacy spanned -0.119 to +0.034 with only 2 of 44 families positive, so a
gradient was tested without a front-loaded end of the range. Mirroring every family to the short side
supplies it -- a family whose long 30-minute mark is negative has a short mark near its negation.
The gradient is then required to hold WITHIN side as well as across sides: if it only appears when
longs and shorts are pooled, it is this sample's 89% up-drift and not the mechanic.

SELECTION IS COMPUTED ENTIRELY ON THE MARKET LEG. Only the fill MASK comes from the limit walk, so
no price improvement can leak into the quantity being explained.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")

COST_PTS, SLIP_PTS = 0.72, 0.25          # real MNQ stack
DELAY_CAP = 480                          # minutes a resting order is tracked for calibration


@njit(cache=True)
def fill_delays(h1, l1, ent1, sig_close, atr_sig, lim_mult, side, cap):
    """Minutes from the entry bar until a resting limit is first touched; -1 if never within cap.

    Fill rate at ANY expiry is then a count over this array, so calibrating the expiry costs one
    walk per family instead of one per candidate expiry."""
    n = len(ent1)
    m = len(l1)
    out = np.full(n, -1, np.int64)
    for k in range(n):
        a = ent1[k]
        if a < 1 or a >= m - 2 or not np.isfinite(atr_sig[k]) or atr_sig[k] <= 0:
            continue
        lvl = sig_close[k] - side * lim_mult * atr_sig[k]
        end = min(m - 1, a + cap)
        j = a
        while j <= end:
            if side > 0:
                if l1[j] <= lvl:
                    out[k] = j - a
                    break
            else:
                if h1[j] >= lvl:
                    out[k] = j - a
                    break
            j += 1
    return out


@njit(cache=True)
def walk(o1, h1, l1, c1, ent1, sig_close, atr_sig, lim_mult, expiry_min, stop_mult, tp_r,
         max_hold_min, mark_min, side, cost, slip):
    """Both mechanics, both sides, identical exits. lim_mult == 0 -> MARKET at the next open.

    Returns per signal: filled, R, mark-to-market R at +mark_min, minutes held."""
    n = len(ent1)
    m = len(c1)
    filled = np.zeros(n, np.int64)
    R = np.full(n, np.nan)
    Rk = np.full(n, np.nan)
    held = np.zeros(n, np.int64)
    for k in range(n):
        a = ent1[k]
        if a < 1 or a >= m - 2 or not np.isfinite(atr_sig[k]) or atr_sig[k] <= 0:
            continue
        risk = stop_mult * atr_sig[k]
        if lim_mult <= 0.0:
            px = o1[a] + side * slip
            j0 = a
        else:
            lvl = sig_close[k] - side * lim_mult * atr_sig[k]
            j0 = -1
            end = min(m - 1, a + expiry_min)
            j = a
            while j <= end:
                if side > 0:
                    if l1[j] <= lvl:
                        j0 = j
                        break
                else:
                    if h1[j] >= lvl:
                        j0 = j
                        break
                j += 1
            if j0 < 0:
                continue
            px = lvl + side * slip
        filled[k] = 1
        stop = px - side * risk
        tgt = px + side * tp_r * risk if tp_r > 0 else (1e18 if side > 0 else -1e18)
        end = min(m - 1, j0 + max_hold_min)
        j = j0
        out = 0.0
        done = False
        while j <= end:
            if side > 0:
                if l1[j] <= stop:
                    out = stop - slip
                    done = True
                    break
                if h1[j] >= tgt:
                    out = tgt - slip
                    done = True
                    break
            else:
                if h1[j] >= stop:
                    out = stop + slip
                    done = True
                    break
                if l1[j] <= tgt:
                    out = tgt + slip
                    done = True
                    break
            j += 1
        if not done:
            j = end
            out = c1[j] - side * slip
        R[k] = (side * (out - px) - cost) / risk
        held[k] = j - j0
        jk = min(m - 1, j0 + mark_min)
        if jk > j:
            jk = j
        Rk[k] = (side * (c1[jk] - px) - cost) / risk
    return filled, R, Rk, held


# ------------------------------------------------------------------------------------------------
# The declared signal ladder. V49's, with ONE correction: `roc.up/dn` cut at a WHOLE-SAMPLE
# np.nanquantile, which is a threshold that reads the future. Replaced with an EXPANDING quantile,
# which is what the truncation audit requires. Every rule reads only bars up to the signal bar.
# ------------------------------------------------------------------------------------------------
def signals(P, min_n=150):
    import pandas as pd
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    atr = P["atr"]
    S = pd.Series(c)
    out = {}

    def add(name, mask):
        m = np.asarray(mask, bool).copy()
        m[:1000] = False
        m[-50:] = False
        m &= np.isfinite(atr) & (atr > 0)
        if m.sum() >= min_n:
            out[name] = np.flatnonzero(m).astype(np.int64)

    for s in range(4):
        r = np.random.default_rng(100 + s)
        add(f"null.random{s}", r.random(len(c)) < 0.004)

    for n in (10, 20, 30, 55, 100, 200):
        hi = pd.Series(h).rolling(n).max().shift(1).to_numpy()
        add(f"don.break{n}", h > hi)
        lo = pd.Series(l).rolling(n).min().shift(1).to_numpy()
        add(f"don.low{n}", l < lo)

    for n in (7, 14, 28):
        d = S.diff()
        g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        b = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rsi = (100 - 100/(1 + g/b.replace(0, np.nan))).to_numpy()
        add(f"rsi.lo{n}", rsi < 30)
        add(f"rsi.hi{n}", rsi > 70)

    for n in (20, 50, 200):
        e = S.ewm(span=n, adjust=False).mean().to_numpy()
        add(f"ema.above{n}", (c > e) & (np.roll(c, 1) <= np.roll(e, 1)))
        add(f"ema.below{n}", (c < e) & (np.roll(c, 1) >= np.roll(e, 1)))

    for n in (12, 48, 192):
        roc = S.pct_change(n)
        qhi = roc.expanding(min_periods=500).quantile(0.90).shift(1).to_numpy()
        qlo = roc.expanding(min_periods=500).quantile(0.10).shift(1).to_numpy()
        rv = roc.to_numpy()
        add(f"roc.up{n}", rv > qhi)
        add(f"roc.dn{n}", rv < qlo)

    r1 = np.concatenate(([np.nan], np.diff(np.log(np.maximum(c, 1e-9)))))
    sd = pd.Series(r1).rolling(240, min_periods=60).std().to_numpy()
    z = np.where(sd > 0, r1 / sd, np.nan)
    for t in (2.0, 3.0):
        add(f"shock.up{t}", z >= t)
        add(f"shock.dn{t}", z <= -t)

    gap = np.concatenate(([np.nan], o[1:] - c[:-1]))
    gz = gap / np.where(atr > 0, atr, np.nan)
    add("gap.up", gz > 0.5)
    add("gap.dn", gz < -0.5)

    rng20 = pd.Series(h - l).rolling(20, min_periods=5).mean().to_numpy()
    add("bar.wide", (h - l) > 2.0 * rng20)
    add("bar.narrow", (h - l) < 0.5 * rng20)
    add("bar.closehi", ((c - l) / np.maximum(h - l, 1e-9)) > 0.9)
    add("bar.closelo", ((c - l) / np.maximum(h - l, 1e-9)) < 0.1)

    mid = S.rolling(20).mean(); sdv = S.rolling(20).std()
    add("bb.upper", c > (mid + 2 * sdv).to_numpy())
    add("bb.lower", c < (mid - 2 * sdv).to_numpy())
    return out
