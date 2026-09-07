"""V67 -- what is predictable about a MOVEMENT, as opposed to a price.

THE QUESTION, STATED SO IT CAN FAIL. "Predict the movement, not the price" is only meaningful once
"movement" is decomposed into targets that are separately measurable. Seven are declared here, and
the direction target is included deliberately as the CONTROL that prior work says should fail, so
the contrast is measured rather than assumed:

    mag    |net log return| over h            magnitude of the net move
    rv     realised vol over h                magnitude, smoother
    rng    (max high - min low) / ATR         range expansion
    er     |net| / sum|steps|                 STRAIGHTNESS -- the path-shape target
    mfe    max favourable excursion in ATR    the upside envelope
    mae    max adverse excursion in ATR       the downside envelope
    ttb    bars to first touch of +/-1 ATR    DURATION -- never tested on this branch
    dir    sign of the net move               THE CONTROL, expected to be null

THE PRIORS THIS HAS TO BEAT, ALL FROM THIS BRANCH'S OWN RECORD:
  * `STUDY_V22`: the VIX forecasts the SIZE of the next move (IC +0.63/+0.78 against forward
    realised vol) and NOT its straightness (research-to-locked IC correlation -0.638, sign kept 21%).
    So `mag` and `rv` are expected to be predictable and `er` is expected not to be.
  * `STUDY_V28`: forward efficiency ratio is NOT forecastable -- in-sample IC 0.41-0.70 collapsing
    to -0.017..+0.040 out of sample -- and NOTHING ever beat simply reading CHOP(14) TODAY. That
    trivial baseline is therefore computed for EVERY target here, and a model that cannot beat the
    trailing realisation of its own target has found nothing.
  * `STUDY_V27`: an HMM read the standard way is a two-sided filter. Parameters must come from a
    block ending before the labelled bar and the FILTERED posterior used, never smoothed or Viterbi
    -- and the two agree on 96-97% of bars, which is why the leak is easy to miss.
  * `STUDY_V47`: overlapping horizons make a naive t-statistic meaningless; Newey-West at lag h
    deflates it by 1.9x to 3.2x here.

AND A FORECAST THAT CHANGES NO DECISION IS NOT A RESULT. Part C takes whatever survives and asks
whether it improves a stop, because `STUDY_V22` already showed the one place a magnitude forecast
pays: an ATR stop is BACKWARD-looking and volatility mean-reverts, so heat in ATR units is 1.8-2.2x
larger when volatility sits LOW in its own distribution.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61sess", "research/v22", "research/v27", "research/v66"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import sess_core as SC        # noqa: E402
import v22vol as VV           # noqa: E402
import v27hmm as H            # noqa: E402

HORIZONS = (4, 16, 48, 96)            # 1h, 4h, 12h, 1 day on 15-minute bars
TARGETS = ("mag", "rv", "rng", "er", "mfe", "mae", "ttb", "dir")


def load(tf=15):
    return SC.build(tf)


# ------------------------------------------------------------------ targets
def build_targets(D, h):
    """Forward targets over the next h bars, measured from bar t's CLOSE.

    Every one is a LABEL, so it reads the future by construction -- that is what a target is. The
    causality that matters is that no FEATURE reads it, which the audit checks.
    """
    o, hi, lo, c, atr = D["o"], D["h"], D["l"], D["c"], D["atr"]
    n = len(c)
    lc = np.log(np.maximum(c, 1e-12))
    step = np.diff(lc, prepend=lc[0])

    fwd = np.full(n, np.nan)
    absum = np.full(n, np.nan)
    rvv = np.full(n, np.nan)
    hh = np.full(n, np.nan)
    ll = np.full(n, np.nan)
    s = pd.Series(step)
    # sum of the NEXT h steps, and of their absolute values
    fwd[:n - h] = s.rolling(h).sum().to_numpy()[h:]
    absum[:n - h] = s.abs().rolling(h).sum().to_numpy()[h:]
    rvv[:n - h] = s.rolling(h).std(ddof=1).to_numpy()[h:] * np.sqrt(h)
    hh[:n - h] = pd.Series(hi).rolling(h).max().to_numpy()[h:]
    ll[:n - h] = pd.Series(lo).rolling(h).min().to_numpy()[h:]

    a = np.maximum(atr, 1e-12)
    T = {}
    T["mag"] = np.abs(fwd) * 100.0
    T["rv"] = rvv * 100.0
    T["rng"] = (hh - ll) / a
    with np.errstate(invalid="ignore", divide="ignore"):
        T["er"] = np.abs(fwd) / np.maximum(absum, 1e-12)
    T["mfe"] = (hh - c) / a
    T["mae"] = (c - ll) / a
    T["dir"] = np.sign(fwd)
    T["ttb"] = _time_to_touch(hi, lo, c, a, h)
    for k in T:
        T[k] = np.asarray(T[k], float)
        T[k][n - h:] = np.nan
    return T


def _time_to_touch(hi, lo, c, a, h):
    """Bars until price first trades +/-1 ATR away from this bar's close, censored at h.

    A duration target. Censoring at h is why it is reported alongside the touch RATE -- a mean of a
    censored variable is not a mean of the thing it censors.
    """
    n = len(c)
    out = np.full(n, np.nan)
    for i in range(n - h):
        up = c[i] + a[i]
        dn = c[i] - a[i]
        k = h
        for j in range(i + 1, i + h + 1):
            if hi[j] >= up or lo[j] <= dn:
                k = j - i
                break
        out[i] = k
    return out


# ------------------------------------------------------------------ the trivial baseline
def trailing_baseline(D, h):
    """For every target, the SAME quantity measured over the PREVIOUS h bars.

    `STUDY_V28` measured that nothing ever beat reading CHOP(14) today. So the bar a model has to
    clear is not zero, it is the trailing realisation of its own target.
    """
    o, hi, lo, c, atr = D["o"], D["h"], D["l"], D["c"], D["atr"]
    lc = np.log(np.maximum(c, 1e-12))
    step = pd.Series(np.diff(lc, prepend=lc[0]))
    a = np.maximum(atr, 1e-12)
    net = step.rolling(h).sum().to_numpy()
    ab = step.abs().rolling(h).sum().to_numpy()
    hh = pd.Series(hi).rolling(h).max().to_numpy()
    ll = pd.Series(lo).rolling(h).min().to_numpy()
    B = {}
    B["mag"] = np.abs(net) * 100.0
    B["rv"] = step.rolling(h).std(ddof=1).to_numpy() * np.sqrt(h) * 100.0
    B["rng"] = (hh - ll) / a
    with np.errstate(invalid="ignore", divide="ignore"):
        B["er"] = np.abs(net) / np.maximum(ab, 1e-12)
    B["mfe"] = (hh - c) / a
    B["mae"] = (c - ll) / a
    B["dir"] = np.sign(net)
    B["ttb"] = np.full(len(c), np.nan)          # no trailing analogue; handled in the runner
    return B


# ------------------------------------------------------------------ statistics
def newey_west_t(x, y, lag):
    """Spearman-style IC is reported separately; this is the NW t on the standardised regression.

    Overlapping horizons make a naive t meaningless -- `STUDY_V47` measured the deflation at 1.9x
    to 3.2x -- so every t reported in this study passes through here.
    """
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 50:
        return np.nan, np.nan
    xs = (x[m] - x[m].mean()) / max(x[m].std(ddof=1), 1e-12)
    ys = (y[m] - y[m].mean()) / max(y[m].std(ddof=1), 1e-12)
    n = len(xs)
    b = float((xs * ys).sum() / (xs * xs).sum())
    e = ys - b * xs
    u = xs * e
    s = float((u * u).sum())
    for L in range(1, int(lag) + 1):
        w = 1.0 - L / (lag + 1.0)
        s += 2.0 * w * float((u[L:] * u[:-L]).sum())
    var = s / max(((xs * xs).sum()) ** 2, 1e-12)
    return b, b / max(np.sqrt(max(var, 1e-30)), 1e-12)


def ic(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 50:
        return np.nan
    return float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman"))


def bh(pvals, q=0.10):
    p = np.asarray(pvals, float)
    ok = np.isfinite(p)
    idx = np.flatnonzero(ok)
    order = idx[np.argsort(p[idx])]
    m = len(order)
    keep = np.zeros(len(p), bool)
    thr = 0.0
    for i, j in enumerate(order, 1):
        if p[j] <= q * i / m:
            thr = p[j]
    if thr > 0:
        keep[ok] = p[ok] <= thr
    return keep, thr
