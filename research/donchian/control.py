"""Matched control: the only defensible scoring baseline for this family.

A random-entry book with the SAME side mix, SAME ATR-scaled geometry and SAME
minute-of-day distribution prices in, all at once: drift, costs, barrier width,
session timing AND the engine's own geometric bias. Comparing a rule to zero
tests the geometry; comparing it to this tests the RULE.

Doctrine (CLAUDE.md): run this as a RESEARCH GATE, in front, not as a final check.
"""
import numpy as np, pandas as pd
from engine import build_walk, simulate, stats, atr


def matched_control(df, walk, tr, n_draws=400, seed=0, cost_pts=2.0,
                    slip_pts=0.25, max_hold=16, flat_tod=660, atr_n=14,
                    stop_mult=1.5, targ_mult=2.0, pool_idx=None):
    """Draw `n_draws` synthetic books matching the real book's minute-of-day
    and side composition. Returns the distribution of mean net P&L per trade."""
    a = atr(df, atr_n)
    tod = df.tod.values; sess = df.sess.values
    m = len(tr)
    if m == 0:
        return np.array([]), np.nan

    # eligible universe: any bar sharing the real book's minute-of-day set,
    # with a usable ATR and a forward walk
    tods = np.unique(tod[tr.sig_bar.values])
    elig = np.isin(tod, tods) & ~np.isnan(a) & (a > 0) & ~np.isnan(walk["opens"][:, 0])
    if pool_idx is not None:
        elig &= pool_idx
    # match the minute-of-day HISTOGRAM, not just the set
    want = pd.Series(tod[tr.sig_bar.values]).value_counts()
    by_tod = {t: np.where(elig & (tod == t))[0] for t in want.index}
    sides = tr.side.values

    rng = np.random.default_rng(seed)
    means = np.empty(n_draws)
    for d in range(n_draws):
        picks = []
        for t, k in want.items():
            pool = by_tod[t]
            if len(pool) == 0:
                continue
            picks.append(rng.choice(pool, size=int(k), replace=True))
        idx = np.concatenate(picks) if picks else np.array([], dtype=int)
        if len(idx) == 0:
            means[d] = np.nan; continue
        side = rng.permutation(sides)[:len(idx)] if len(sides) >= len(idx) else \
            rng.choice(sides, size=len(idx))
        side = side.astype(np.float64)
        fill = walk["opens"][idx, 0]
        entry = fill + side * slip_pts
        av = a[idx]
        stop = entry - side * stop_mult * av
        targ = entry + side * targ_mult * av if targ_mult > 0 else \
            np.where(side > 0, np.inf, -np.inf)
        c = simulate(walk, idx, side, entry, stop, targ, max_hold=max_hold,
                     flat_tod=flat_tod, cost_pts=cost_pts)
        means[d] = c.net.mean() if len(c) else np.nan
    means = means[~np.isnan(means)]
    real = tr.net.mean()
    p = float((means >= real).mean()) if len(means) else np.nan
    return means, p


def report(tr, means, p, label=""):
    if len(tr) == 0 or len(means) == 0:
        return f"{label:<34} NO TRADES"
    real = tr.net.mean()
    z = (real - means.mean()) / means.std(ddof=1) if means.std(ddof=1) > 0 else 0.0
    return (f"{label:<34} n={len(tr):>5,}  exp={real:>+7.2f}  ctrl={means.mean():>+7.2f}"
            f"  excess={real-means.mean():>+7.2f}  z={z:>+6.2f}  p={p:.4f}")
