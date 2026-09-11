"""V49 -- where does the limit entry stop helping? One walker, two mechanics, identical exits.

THE HYPOTHESIS. The limit entry's advantage over a market entry is a DECREASING FUNCTION OF THE
SIGNAL'S OWN IMMEDIACY. A resting limit only fills after an adverse excursion, so it systematically
discards trades that move in your favour at once. Where a signal's edge is back-loaded or absent,
waiting costs nothing and buys a better price; where the edge is front-loaded, waiting removes
exactly the winners. `STUDY_LIMIT_ENTRY` established the two endpoints -- additive on a null signal,
substitutive on a good one. This measures the GRADIENT BETWEEN THEM and asks where it crosses zero.

ONE WALKER, TWO MECHANICS. Both entries are priced through the SAME exits, the same ATR stop from
the same signal-bar ATR, the same max hold and the same costs; only the fill differs. Using two
engines would put a convention gap inside the very quantity being measured -- which is exactly the
2.1x and 22.9x gaps this branch has already caught between engines.

THE TRUE 1-MINUTE PATH. `STUDY_ATME_LIVE` re-ran a selected 5-minute limit configuration on the
minute path and the result fell FIVEFOLD, from +0.331 R to -0.003, purely from exit ordering. A
limit-entry question settled on the bars that also decide the exits is not settled. Every trade
below is walked on NQ 1-minute data.

IMMEDIACY IS MEASURED ON THE MARKET-ENTRY LEG, as the mean mark-to-market R at +K minutes after the
fill. A ratio of early edge to total edge would be unstable wherever the denominator is near zero,
so the early edge itself is used and the total is reported beside it.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")

COST_PTS, SLIP_PTS = 0.72, 0.25          # real MNQ stack, not limit_entry's broker-only COMM


@njit(cache=True)
def walk(o1, h1, l1, c1, ent1, sig_close, atr_sig, lim_mult, expiry_min, stop_mult, tp_r,
         max_hold_min, mark_min, cost, slip):
    """Both mechanics. lim_mult == 0 -> MARKET at the next open. Otherwise a resting limit
    `lim_mult` x ATR below the signal close, live for `expiry_min` minutes.

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
            px = o1[a] + slip
            j0 = a
        else:
            lvl = sig_close[k] - lim_mult * atr_sig[k]
            j0 = -1
            end = min(m - 1, a + expiry_min)
            j = a
            while j <= end:
                if l1[j] <= lvl:
                    j0 = j
                    break
                j += 1
            if j0 < 0:
                continue
            px = lvl + slip
        filled[k] = 1
        stop = px - risk
        tgt = px + tp_r * risk if tp_r > 0 else 1e18
        end = min(m - 1, j0 + max_hold_min)
        j = j0
        out = 0.0
        while j <= end:
            if l1[j] <= stop:
                out = stop - slip
                break
            if h1[j] >= tgt:
                out = tgt - slip
                break
            j += 1
        else:
            j = end
            out = c1[j] - slip
        if j > end:
            j = end
            out = c1[j] - slip
        R[k] = (out - px - cost) / risk
        held[k] = j - j0
        jk = min(m - 1, j0 + mark_min)
        if jk > j:
            jk = j
        Rk[k] = (c1[jk] - px - cost) / risk
    return filled, R, Rk, held


# ------------------------------------------------------------------------------------------------
# The declared signal ladder. Deliberately spans null to strong so the gradient has a range to
# live on. Every rule is long-only and reads only bars up to and including the signal bar.
# ------------------------------------------------------------------------------------------------
def signals(P):
    import pandas as pd
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    atr = P["atr"]
    S = pd.Series(c)
    out = {}

    def add(name, mask):
        m = np.asarray(mask, bool).copy()
        m[:300] = False
        m[-50:] = False
        m &= np.isfinite(atr) & (atr > 0)
        if m.sum() >= 150:
            out[name] = np.flatnonzero(m).astype(np.int64)

    rng = np.random.default_rng(0)
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
        roc = S.pct_change(n).to_numpy()
        add(f"roc.up{n}", roc > np.nanquantile(roc, 0.90))
        add(f"roc.dn{n}", roc < np.nanquantile(roc, 0.10))

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
