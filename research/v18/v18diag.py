"""Cointegration and correlation diagnostics, hand-rolled -- statsmodels is not installed here.

WHAT CAN AND CANNOT BE ASKED WITH ONE INSTRUMENT. Pairs cointegration -- Engle-Granger or Johansen
on two price series -- needs two series. `data/` currently holds NQ 1-minute and NQ 5-minute and
nothing else, so that test is not available and is not faked. What IS available, and is the
question a trend follower actually needs answered, is whether the series the strategy trades has
persistent deviations from its own long average or mean-reverting ones.

AND THERE IS A TRAP IN ASKING IT THE OBVIOUS WAY. Price and its own EWMA are cointegrated BY
CONSTRUCTION: an EWMA is a weighted average of past prices, so price minus EWMA is a weighted sum
of past price CHANGES (Zakamulin, and verified exactly on this branch in STUDY_RULE_ANATOMY). If
returns are I(0) then the spread is I(0) and an ADF test rejects a unit root essentially always.
That is a definition, not a discovery, and reporting it as evidence of mean reversion would be
wrong. The informative quantity is not WHETHER the spread reverts but HOW FAST -- its AR(1)
half-life -- measured against how long the strategy actually holds. A trend system whose median
hold is longer than the spread's half-life is holding through the reversion it is supposed to ride.

So this module reports, in order:
  1. ADF on the EWMAC spread, with the caveat above attached to the number.
  2. The AR(1) HALF-LIFE of that spread, which is the number that decides anything.
  3. The HURST exponent and the VARIANCE RATIO at several horizons -- direct tests of whether
     returns trend (H > 0.5, VR > 1) or revert (H < 0.5, VR < 1) at the horizons being traded.
  4. Correlations that matter for this strategy: to buy-and-hold (is it just beta?), the signal's
     information coefficient at several horizons, and the overlap between the EWMA filter and the
     Donchian trigger, because this branch has caught its own pools containing the same condition
     twice on three separate occasions.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")


def adf(x, maxlag=None):
    """Augmented Dickey-Fuller with a constant, t-statistic on the lagged level.

    Hand-rolled least squares: dx_t = a + b*x_{t-1} + sum(g_i * dx_{t-i}) + e. The statistic is
    t(b). Critical values are MacKinnon's for the constant-only case; they are hard-coded because
    the alternative is an unavailable dependency, and they are the only ones this uses.
    """
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if maxlag is None:
        maxlag = int(np.ceil(12 * (n / 100.0) ** 0.25))
        maxlag = min(maxlag, max(1, n // 20))
    dx = np.diff(x)
    m = len(dx) - maxlag
    if m < 20:
        return np.nan, np.nan, maxlag
    y = dx[maxlag:]
    cols = [np.ones(m), x[maxlag:-1]]
    for i in range(1, maxlag + 1):
        cols.append(dx[maxlag - i:-i])
    X = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = m - X.shape[1]
    s2 = float(resid @ resid) / dof
    xtx_inv = np.linalg.pinv(X.T @ X)
    se = np.sqrt(s2 * xtx_inv[1, 1])
    t = float(beta[1] / se) if se > 0 else np.nan
    # MacKinnon (2010), constant only, asymptotic
    crit = {"1%": -3.43, "5%": -2.86, "10%": -2.57}
    return t, crit, maxlag


def half_life(x):
    """AR(1) half-life of mean reversion: dx_t = a + b*x_{t-1}; hl = -ln(2)/ln(1+b)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    dx = np.diff(x)
    X = np.column_stack([np.ones(len(dx)), x[:-1]])
    beta, *_ = np.linalg.lstsq(X, dx, rcond=None)
    b = beta[1]
    if b >= 0 or not np.isfinite(b):
        return np.inf
    return float(-np.log(2.0) / np.log1p(b))


def hurst(x, lags=(2, 4, 8, 16, 32, 64, 128)):
    """Hurst by the rescaled-range-free variance-of-differences estimator. 0.5 = random walk."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    lg, tau = [], []
    for L in lags:
        if L >= len(x) // 4:
            continue
        d = x[L:] - x[:-L]
        s = np.std(d, ddof=0)
        if s > 0:
            lg.append(np.log(L))
            tau.append(np.log(s))
    if len(lg) < 3:
        return np.nan
    return float(np.polyfit(lg, tau, 1)[0])


def variance_ratio(r, q):
    """Lo-MacKinlay VR(q) with the heteroskedasticity-robust z. VR > 1 = trending."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 4 * q:
        return np.nan, np.nan
    mu = r.mean()
    va = ((r - mu) ** 2).sum() / (n - 1)
    agg = np.convolve(r, np.ones(q), mode="valid")
    m = q * (n - q + 1) * (1 - q / n)
    vq = ((agg - q * mu) ** 2).sum() / m
    vr = vq / va if va > 0 else np.nan
    # heteroskedasticity-consistent standard error
    # Lo-MacKinlay's heteroskedasticity-consistent theta*(q):
    #   delta(j) = SUM (r_t-mu)^2 (r_{t-j}-mu)^2  /  [ SUM (r_t-mu)^2 ]^2
    # The denominator is the SQUARE OF THE SUM, with no extra 1/n. Dividing by n as well makes
    # every delta n times too large, theta n times too large and the z sqrt(n) times too small --
    # which on 30,000 bars prints z = 0.0 for every series and looks like a random walk everywhere.
    d = (r - mu) ** 2
    den = float(d.sum()) ** 2
    theta = 0.0
    for j in range(1, q):
        num = float((d[j:] * d[:-j]).sum())
        dj = num / den if den > 0 else 0.0
        theta += (2.0 * (q - j) / q) ** 2 * dj
    z = (vr - 1.0) / np.sqrt(theta) if theta > 0 else np.nan
    return float(vr), float(z)


def nw_corr(x, y, lag=None):
    """Correlation plus a Newey-West t, for overlapping forward returns."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 30:
        return np.nan, np.nan, n
    r = float(np.corrcoef(x, y)[0, 1])
    if lag is None:
        lag = max(1, int(n ** (1 / 3)))
    xs = (x - x.mean()) / x.std(ddof=0)
    ys = (y - y.mean()) / y.std(ddof=0)
    u = xs * ys
    g0 = float((u - u.mean()) @ (u - u.mean())) / n
    s = g0
    for L in range(1, lag + 1):
        g = float((u[L:] - u.mean()) @ (u[:-L] - u.mean())) / n
        s += 2.0 * (1.0 - L / (lag + 1.0)) * g
    se = np.sqrt(max(s, 1e-18) / n)
    return r, float(r / se), n
