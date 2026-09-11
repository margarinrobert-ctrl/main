"""Allocation across the legs that already exist, with the weights chosen out of sample.

WHY THIS AND NOT ANOTHER SEARCH. `STUDY_TOP5` ended "what would move it is MORE RESERVED
BLOCKS, not more strategies"; `STUDY_INSTITUTIONAL_FRONTIER` found the strongest honest object
on this branch is a BOOK of the legs that already pass, correlating 0.01-0.19; and
`STUDY_SEMIVARIANCE` / `STUDY_V61_US30` both recorded a decorrelated leg making a book WORSE.
No study here has ever chosen portfolio weights on research and read them once on reserved.

THE SPLIT, AND WHAT IT IS AND IS NOT OUT OF SAMPLE FOR. Each leg carries its own block labels.
The book's research window is every calendar date at or before

    cut = min over legs of (the last date of that leg's own research block)

so on every book-research date EVERY leg is inside its own research block. Weights are fitted
there and read once after it. A leg whose own research block extends past `cut` still had its
PARAMETERS chosen using dates in the book's reserved window -- so the absolute level of the
reserved read is NOT a clean out-of-sample number for the legs. It is clean for the ALLOCATION,
which is the only thing this study varies: every arm, including the equal-weight null, carries
the identical leg contamination, so the COMPARISON between arms is honest even though the level
is not. Say that whenever a number from here is quoted.

THE NULL IS EQUAL WEIGHT, and a random draw from the same simplex is the second null -- the
same instrument as a same-selectivity random filter. A scheme that cannot beat a coin flip over
weights has not learnt anything about the covariance.

THE UNIT is percent of entry price at ONE unit per leg per trade, zero-filled over every date
in the book's calendar, which is `STUDY_TOP5`'s convention and the only one comparable across
six instruments and four contract specifications.
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LEGS = os.path.join(HERE, "legs.pkl")


# ---------------------------------------------------------------- loading -------------------
def load():
    with open(LEGS, "rb") as fh:
        return pickle.load(fh)


def _sess_dates(tr):
    return pd.to_datetime(tr["sess"].astype(str), format="%Y%m%d")


def leg_daily(rec):
    """Daily percent-of-price at one unit, indexed by calendar date, plus the block label."""
    tr = rec["tr"].copy()
    tr["date"] = _sess_dates(tr)
    g = tr.groupby("date")
    r = g["pct"].sum()
    # a date's block is the block its trades fall in (a date never straddles two)
    b = g["block"].first()
    return r, b


def research_cut(legs, names=None):
    """The last date on which EVERY named leg is still inside its own research block."""
    ends = []
    for k, rec in legs.items():
        if names is not None and k not in names:
            continue
        r, b = leg_daily(rec)
        m = b == rec["is_block"]
        if not m.any():
            continue
        ends.append(r.index[m].max())
    return min(ends)


def panel(legs, names, cut=None):
    """A (dates x legs) matrix of daily percent-of-price, zero-filled on the union calendar."""
    series, blocks = {}, {}
    for k in names:
        r, b = leg_daily(legs[k])
        series[k] = r
        blocks[k] = b
    idx = sorted(set().union(*[s.index for s in series.values()]))
    idx = pd.DatetimeIndex(idx)
    X = pd.DataFrame({k: series[k].reindex(idx).fillna(0.0) for k in names}, index=idx)
    # a leg contributes zeros only INSIDE its own span; before/after it is absent (NaN)
    span = pd.DataFrame({k: (idx >= series[k].index.min()) & (idx <= series[k].index.max())
                         for k in names}, index=idx)
    return X, span


# ---------------------------------------------------------------- weights -------------------
def _shrink_cov(X, lam=None):
    """Covariance with the correlation shrunk toward the identity. lam=None -> Ledoit-Wolf-ish
    constant chosen from the sample size, which is the honest default at 8 legs."""
    S = np.cov(X, rowvar=False)
    d = np.sqrt(np.diag(S))
    d[d <= 0] = 1e-12
    C = S / np.outer(d, d)
    n, p = X.shape
    if lam is None:
        lam = min(1.0, p / max(1.0, n))          # more legs per observation -> shrink harder
    C = (1 - lam) * C + lam * np.eye(p)
    return C * np.outer(d, d), C, d, lam


def _norm(w):
    w = np.asarray(w, float)
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else np.full(len(w), 1.0 / len(w))


def w_equal(X):
    return np.full(X.shape[1], 1.0 / X.shape[1])


def w_invvol(X):
    s = X.std(axis=0, ddof=1)
    s = np.where(s > 0, s, np.inf)
    return _norm(1.0 / s)


def w_riskparity(X, iters=2000):
    S, _, _, _ = _shrink_cov(X)
    p = S.shape[0]
    w = np.full(p, 1.0 / p)
    for _ in range(iters):
        m = S @ w
        rc = w * m
        tgt = rc.mean()
        w = np.clip(w * (tgt / np.maximum(rc, 1e-18)) ** 0.1, 1e-8, None)
        w /= w.sum()
    return w


def w_minvar(X):
    S, _, _, _ = _shrink_cov(X)
    try:
        w = np.linalg.solve(S, np.ones(S.shape[0]))
    except np.linalg.LinAlgError:
        return w_equal(X)
    return _norm(w)


def w_meanvar(X):
    S, _, _, _ = _shrink_cov(X)
    mu = X.mean(axis=0).to_numpy() if hasattr(X, "mean") else X.mean(axis=0)
    try:
        w = np.linalg.solve(S, mu)
    except np.linalg.LinAlgError:
        return w_equal(X)
    return _norm(w)


SCHEMES = dict(equal=w_equal, invvol=w_invvol, riskparity=w_riskparity,
               minvar=w_minvar, meanvar=w_meanvar)


# ---------------------------------------------------------------- scoring -------------------
def book(X, w):
    return (X.to_numpy() if hasattr(X, "to_numpy") else X) @ np.asarray(w, float)


def stats(d, ann=252):
    d = np.asarray(d, float)
    if len(d) < 2 or d.std() == 0:
        return dict(n=len(d), total=float(d.sum()), sharpe=np.nan, dd=np.nan, ret_dd=np.nan)
    eq = np.cumsum(d)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    yrs = len(d) / ann
    return dict(n=len(d), total=float(d.sum()), per_yr=float(d.sum() / yrs),
                sharpe=float(d.mean() / d.std(ddof=1) * np.sqrt(ann)),
                dd=dd, ret_dd=float(d.sum() / dd) if dd > 0 else np.nan)


def block_boot(d, n=4000, block=10, seed=0):
    """Block bootstrap of the mean of a daily series (or of a DIFFERENCE series)."""
    rng = np.random.default_rng(seed)
    d = np.asarray(d, float)
    T = len(d)
    nb = int(np.ceil(T / block))
    out = np.empty(n)
    for i in range(n):
        st = rng.integers(0, max(1, T - block + 1), nb)
        out[i] = np.concatenate([d[s:s + block] for s in st])[:T].mean()
    return out


def rand_weights(p, n=2000, seed=0):
    """Uniform draws from the simplex -- the second null."""
    rng = np.random.default_rng(seed)
    w = rng.dirichlet(np.ones(p), size=n)
    return w
