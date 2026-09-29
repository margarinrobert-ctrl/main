"""Why the profitability goal is not being met, stated as a construction rather than an opinion.

THE DIAGNOSIS, in three layers, each already measured elsewhere on this branch:

1.  ARITHMETIC.  Every leg here earns +0.04 to +0.08 R (`STUDY_V31_MONTECARLO`), and the minimum
    detectable effect at any realistic trade count is LARGER than that (`STUDY_US30_SCALP_0711` §10:
    MDE 10.74 pts against a PF-1.2 requirement of +10.61, and `E[max t | noise]` over a search
    already exceeding the detection threshold).  No single-strategy search can confirm a leg on this
    data.  That is why forty studies end "ships nothing" -- it is a property of effect size against
    sample size, not a failure of effort.

2.  THE QUESTION.  The branch asks a RESEARCH question at the LEG level ("does this beat its matched
    control") and gets no, every time.  `STUDY_ALLOCATION` asked the PORTFOLIO question ("does the
    book beat zero") and got **P(mean<=0) 0.0000-0.0012 on every arm**.  Both are true.  A book of
    N near-uncorrelated legs has Sharpe ~ sqrt(N) x leg Sharpe, and the legs here are measurably
    near-uncorrelated AND STAY THAT WAY -- pairwise rho transfers research-to-reserved at **+0.7051**,
    the most transferable quantity measured on this branch.

3.  CONSTRUCTION -- and this is the fixable one.  `STUDY_ALLOCATION` built its book on a GLOBAL
    research cut, `min` over legs of each leg's own research end = **2021-12-17**, which is set by a
    single leg (APM_VWAP/US30).  Every NQ leg begins 2022-12-27, a year AFTER it.  So the one object
    on this branch that clears zero is built on **11 of 23 legs and excludes the two
    highest-scoring strategies in `STUDY_TOP5`** -- FTM_ORB/NQ (+6.38 %/yr) and V56_CVD/NQ (+7.94) --
    for a calendar bookkeeping reason and not for an evidential one.

THE FIX IS THE HONEST CONSTRUCTION ANYWAY.  Drop the global cut and give every leg its OWN
availability date: a leg may enter the book only on dates AFTER its own research block ends, which
is exactly what a live book does -- you cannot trade a strategy before you have developed it.  That
admits all 23 legs and, as a side effect, REMOVES the caveat `STUDY_ALLOCATION` had to attach to its
own headline ("a leg whose research block extends past the cut had its parameters chosen inside the
book's reserved window, so the absolute level is not a clean out-of-sample number for the legs").
Under per-leg availability every daily return in this book is out of sample for the leg that
produced it.

WHAT THIS IS NOT.  These post-research spans have been read before -- by `STUDY_TOP5` and by
`STUDY_ALLOCATION` -- so this is a DESCRIPTIVE re-read of spent blocks, not a fresh pre-registered
test.  It cannot be quoted as a p-value.  What it can do is measure, correctly, what a book
assembled the way a desk would assemble it actually delivers, and what leverage a stated return
target implies against a drawdown the permutation says to expect.
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LEGS = os.path.join(os.path.dirname(HERE), "alloc", "legs.pkl")
TDY = 252


def load(path=LEGS):
    return pickle.load(open(path, "rb"))


def leg_frame(v):
    """Daily percent-of-entry-price return for one leg, plus the date it becomes AVAILABLE."""
    tr = v["tr"].copy()
    tr["ts"] = pd.to_datetime(tr["ts"])
    res = tr[tr["block"] == v["is_block"]]
    # A leg with no labelled research block (the ISO feeds) is available from its first trade:
    # nothing on this branch was fitted on them.
    avail = (res["ts"].max().normalize() + pd.Timedelta(days=1)) if len(res) else tr["ts"].min().normalize()
    d = tr.groupby(tr["ts"].dt.normalize())["pct"].sum()
    return d, avail


def panel(L):
    """Daily returns and an availability mask, over the union calendar."""
    ser, av = {}, {}
    for k, v in L.items():
        d, a = leg_frame(v)
        name = f"{k[0]}/{k[1]}"
        ser[name], av[name] = d, a
    idx = pd.DatetimeIndex(sorted(set().union(*[s.index for s in ser.values()])))
    R = pd.DataFrame({k: s.reindex(idx).fillna(0.0) for k, s in ser.items()})
    A = pd.DataFrame({k: (idx >= av[k]) for k in ser}, index=idx)
    return R, A, pd.Series(av)


def book(R, A, scheme="equal", vol_win=126, min_legs=2):
    """Equal or causal inverse-vol weights over the legs AVAILABLE on each date."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    if scheme == "invvol":
        # trailing sd, shifted so the weight for day t uses data through t-1 only
        sd = R.rolling(vol_win, min_periods=20).std().shift(1)
        raw = (1.0 / sd.replace(0.0, np.nan)).where(A)
    else:
        raw = A.astype(float).replace(False, np.nan)
    raw = raw.where(A)
    n_ok = A.sum(axis=1)
    raw = raw.div(raw.sum(axis=1), axis=0)
    w[:] = raw.fillna(0.0)
    r = (R * w).sum(axis=1)
    return r[n_ok >= min_legs], w, n_ok


def stats(r, lev=1.0):
    x = r * lev
    if not len(x) or x.std() == 0:
        return {}
    eq = x.cumsum()
    dd = float((np.maximum.accumulate(eq) - eq).max())
    yrs = len(x) / TDY
    return dict(days=len(x), ann_ret=float(x.mean() * TDY), ann_vol=float(x.std() * np.sqrt(TDY)),
                sharpe=float(x.mean() / x.std() * np.sqrt(TDY)), total=float(x.sum()),
                maxdd=dd, ret_dd=float(x.sum() / dd) if dd > 0 else np.nan,
                yrs=yrs, pct_underwater=float(((np.maximum.accumulate(eq) - eq) > 1e-12).mean()))


def perm_dd(r, lev=1.0, n=4000, seed=3):
    """Permutation for the PATH: reshuffle the book's own daily returns."""
    rng = np.random.default_rng(seed)
    x = (r * lev).to_numpy()
    out = np.empty(n)
    for i in range(n):
        eq = np.cumsum(rng.permutation(x))
        out[i] = np.max(np.maximum.accumulate(eq) - eq)
    return out


def block_boot(r, lev=1.0, n=4000, block=10, seed=5):
    """Day-block bootstrap for the EDGE."""
    rng = np.random.default_rng(seed)
    x = (r * lev).to_numpy()
    nb = max(1, len(x) // block)
    out = np.empty(n)
    for i in range(n):
        st = rng.integers(0, max(1, len(x) - block), nb)
        out[i] = np.mean(np.concatenate([x[s:s + block] for s in st]))
    return out
