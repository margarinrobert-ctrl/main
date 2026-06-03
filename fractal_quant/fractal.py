"""Fractal estimators: Hurst (R/S and DFA), FRAMA, and fractal dimension.

These reimplement the formulas in Section 2 of FRACTAL_QUANT_HANDOFF.md and
are cross-checked against the reference fractal_engine.html. To stay faithful
to the reference, standard deviations here are *population* std (ddof=0), which
matches the JavaScript implementation.
"""
from __future__ import annotations

import numpy as np


def _pstd(a: np.ndarray) -> float:
    """Population standard deviation (ddof=0), matching the HTML reference."""
    return float(np.std(a))


# ---------------------------------------------------------------------------
# Hurst exponent via Rescaled-Range (R/S) analysis  (Section 2.2)
# ---------------------------------------------------------------------------
def hurst_rs(series) -> float:
    """Estimate the Hurst exponent of ``series`` via rescaled-range analysis.

    Faithful port of ``hurstRS`` in fractal_engine.html.

    Parameters
    ----------
    series : array-like
        Typically a window of log-returns.

    Returns
    -------
    float
        Slope of ln(avg R/S) regressed on ln(chunk size). ~0.5 for a random
        walk, >0.5 persistent/trending, <0.5 anti-persistent/mean-reverting.
        ``np.nan`` if there is too little data.
    """
    s = np.asarray(series, dtype=float)
    n = s.size
    if n < 40:
        return float("nan")

    # geometric chunk sizes 10, 16, 25, ... up to floor(n/2)
    sizes = []
    sz = 10
    half_n = n // 2
    while sz <= half_n:
        sizes.append(sz)
        sz = int(np.floor(sz * 1.6))
    if not sizes or sizes[-1] < half_n:
        sizes.append(half_n)

    X, Y = [], []
    for sz in sizes:
        chunks = n // sz
        if chunks < 1:
            continue
        acc, c = 0.0, 0
        for k in range(chunks):
            seg = s[k * sz:(k + 1) * sz]
            m = seg.mean()
            cum = np.cumsum(seg - m)
            R = cum.max() - cum.min()
            S = _pstd(seg)
            if S > 1e-12:
                acc += R / S
                c += 1
        if c > 0:
            X.append(np.log(sz))
            Y.append(np.log(acc / c))

    if len(X) < 2:
        return float("nan")

    X = np.asarray(X)
    Y = np.asarray(Y)
    mx, my = X.mean(), Y.mean()
    num = np.sum((X - mx) * (Y - my))
    den = np.sum((X - mx) ** 2)
    return float(num / den) if den > 0 else float("nan")


# ---------------------------------------------------------------------------
# Hurst exponent via Detrended Fluctuation Analysis (DFA)  (Section 7.3)
# ---------------------------------------------------------------------------
def hurst_dfa(series) -> float:
    """Estimate the Hurst exponent via Detrended Fluctuation Analysis.

    DFA is less biased than R/S in small samples (Section 5). Operates on the
    cumulative-sum "profile" of the mean-removed series, fits a linear trend in
    each window, and regresses ln(fluctuation) on ln(window size).
    """
    x = np.asarray(series, dtype=float)
    n = x.size
    if n < 40:
        return float("nan")

    profile = np.cumsum(x - x.mean())

    sizes = []
    sz = 10
    half_n = n // 2
    while sz <= half_n:
        sizes.append(sz)
        sz = int(np.floor(sz * 1.6))
    if not sizes or sizes[-1] < half_n:
        sizes.append(half_n)

    X, Y = [], []
    for sz in sizes:
        chunks = n // sz
        if chunks < 1:
            continue
        rms = []
        t = np.arange(sz)
        for k in range(chunks):
            seg = profile[k * sz:(k + 1) * sz]
            # least-squares linear detrend
            coef = np.polyfit(t, seg, 1)
            fit = np.polyval(coef, t)
            rms.append(np.sqrt(np.mean((seg - fit) ** 2)))
        f = np.mean(rms)
        if f > 1e-12:
            X.append(np.log(sz))
            Y.append(np.log(f))

    if len(X) < 2:
        return float("nan")

    X = np.asarray(X)
    Y = np.asarray(Y)
    mx, my = X.mean(), Y.mean()
    num = np.sum((X - mx) * (Y - my))
    den = np.sum((X - mx) ** 2)
    return float(num / den) if den > 0 else float("nan")


# ---------------------------------------------------------------------------
# FRAMA — Ehlers' Fractal Adaptive Moving Average  (Section 2.3)
# ---------------------------------------------------------------------------
def frama(high, low, close, N: int = 16) -> np.ndarray:
    """Ehlers' Fractal Adaptive Moving Average.

    Faithful port of ``frama`` in fractal_engine.html. ``N`` is forced even;
    uses real highs/lows where present.
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    if N % 2:
        N += 1
    half = N // 2
    m = close.size
    out = np.full(m, np.nan)
    ln2 = np.log(2.0)

    for i in range(m):
        if i < N:
            out[i] = close[i]
            continue
        # older half: indices [i-N+1, i-half]
        h1 = high[i - N + 1:i - half + 1].max()
        l1 = low[i - N + 1:i - half + 1].min()
        # recent half: indices [i-half+1, i]
        h2 = high[i - half + 1:i + 1].max()
        l2 = low[i - half + 1:i + 1].min()
        # full window
        h3 = high[i - N + 1:i + 1].max()
        l3 = low[i - N + 1:i + 1].min()

        n1 = (h1 - l1) / half
        n2 = (h2 - l2) / half
        n3 = (h3 - l3) / N
        D = 1.0
        if n1 > 0 and n2 > 0 and n3 > 0:
            D = (np.log(n1 + n2) - np.log(n3)) / ln2
        a = np.exp(-4.6 * (D - 1.0))
        a = max(0.01, min(1.0, a))
        out[i] = a * close[i] + (1.0 - a) * out[i - 1]
    return out


def fractal_dimension(high, low, close, N: int = 16):
    """Return the per-bar Ehlers fractal dimension D (~1 trend .. 2 noise)."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    if N % 2:
        N += 1
    half = N // 2
    m = close.size
    out = np.full(m, np.nan)
    ln2 = np.log(2.0)
    for i in range(N, m):
        h1 = high[i - N + 1:i - half + 1].max()
        l1 = low[i - N + 1:i - half + 1].min()
        h2 = high[i - half + 1:i + 1].max()
        l2 = low[i - half + 1:i + 1].min()
        h3 = high[i - N + 1:i + 1].max()
        l3 = low[i - N + 1:i + 1].min()
        n1 = (h1 - l1) / half
        n2 = (h2 - l2) / half
        n3 = (h3 - l3) / N
        if n1 > 0 and n2 > 0 and n3 > 0:
            out[i] = (np.log(n1 + n2) - np.log(n3)) / ln2
    return out


def rolling_hurst(logr, window: int = 120, method: str = "rs") -> np.ndarray:
    """Rolling Hurst exponent over ``logr`` (Section 2.2 windowing).

    H[i] is computed on logr[i-window+1 : i+1]; entries before ``window`` are NaN.
    """
    logr = np.asarray(logr, dtype=float)
    n = logr.size
    H = np.full(n, np.nan)
    est = hurst_dfa if method == "dfa" else hurst_rs
    for i in range(window, n):
        H[i] = est(logr[i - window + 1:i + 1])
    return H
