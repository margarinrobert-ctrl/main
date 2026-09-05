"""Information coefficient with Newey-West and Benjamini-Hochberg.

TWO THINGS MAKE A NAIVE IC MEANINGLESS HERE.
  1. OVERLAP. A forward return over h bars, measured at every bar, gives h-1 bars of induced
     autocorrelation. The ordinary t-statistic on that is inflated by roughly sqrt(h). Newey-West
     with h lags is the minimum correction.
  2. MULTIPLICITY. 36 features x 5 horizons x 2 blocks is 360 tests; at p<0.05 you expect 18
     "discoveries" from noise. Benjamini-Hochberg on the whole family is what makes the count
     mean something.
And the forward return is divided by ATR at the signal bar, so an IC computed over nine years of
an index that tripled is not dominated by the last two.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy import stats


def _nw_se(x, lags):
    """Newey-West standard error of the mean of x."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    n = len(x)
    if n < 30: return np.nan
    e = x - x.mean()
    g0 = float(e @ e) / n
    s = g0
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1.0)
        g = float(e[L:] @ e[:-L]) / n
        s += 2 * w * g
    return np.sqrt(max(s, 0) / n)


def ic_table(F, atr, c, mask, horizons=(1, 4, 8, 16, 32)):
    """Spearman IC per feature per horizon, with a Newey-West t on the per-bar rank product."""
    c = np.asarray(c, float); A = np.maximum(np.asarray(atr, float), 1e-9)
    rows = []
    for h in horizons:
        fwd = (np.r_[c[h:], np.full(h, np.nan)] - c) / A          # forward move in ATR units
        for name, v in F.items():
            v = np.asarray(v, float)
            ok = mask & np.isfinite(v) & np.isfinite(fwd)
            if ok.sum() < 500 or np.nanstd(v[ok]) == 0:
                continue
            x, y = v[ok], fwd[ok]
            rho, _ = stats.spearmanr(x, y)
            # per-observation contribution, so Newey-West has something to correct
            rx = stats.rankdata(x) / len(x) - 0.5
            ry = stats.rankdata(y) / len(y) - 0.5
            prod = rx * ry * 12.0                                  # scaled so mean(prod) ~= rho
            se = _nw_se(prod, lags=max(h, 2))
            t = float(np.mean(prod) / se) if (se and np.isfinite(se) and se > 0) else np.nan
            p = float(2 * (1 - stats.norm.cdf(abs(t)))) if np.isfinite(t) else np.nan
            rows.append(dict(feature=name, h=h, n=int(ok.sum()), ic=float(rho), t=t, p=p))
    R = pd.DataFrame(rows)
    if len(R) == 0: return R
    R = R.sort_values("p").reset_index(drop=True)
    m = len(R)
    R["bh"] = R["p"] * m / (R.index + 1)                           # Benjamini-Hochberg critical
    R["bh"] = R["bh"][::-1].cummin()[::-1]
    R["pass_bh"] = R["bh"] < 0.05
    return R
