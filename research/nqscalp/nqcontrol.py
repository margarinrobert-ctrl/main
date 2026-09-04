"""Matched control for the NQ Scalping System.

Random entries drawn from the SAME session pool, with the same side mix and the
same minute-of-day histogram as the real book, pushed through the IDENTICAL exit
machinery (same ATR geometry read at the drawn signal bar, same trailing stop,
same costs, same one-position-at-a-time constraint).

This is the test that separates "the signal is good" from "the exit mechanic
harvests intrabar noise". Scoring against zero is invalid on any barrier engine
(the repo measured a 29-33% false-positive rate doing that); the control prices
in drift, costs, barrier width, session timing and the engine's own geometry.
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/home/user/main/research/nqscalp")
import nqs


def pool_mask(df, I, p, mask=None):
    (lo, sh), in_sess = nqs.conditions(df, I, p)
    fin = np.isfinite(I["atr"]) & np.isfinite(I["trend"]) & np.isfinite(I["d"])
    ok = in_sess & fin
    ok[-1] = False
    if mask is not None:
        ok = ok & mask
    return ok


def draw(df, I, p, tr, ok, rng):
    """One control book: same n, same side mix, same minute-of-day histogram."""
    chi = (df.tod.values - nqs.NY_MINUS_CHICAGO) % 1440
    n = len(df)
    lo = np.zeros(n, bool); sh = np.zeros(n, bool)
    pool_by_tod = {}
    idx_ok = np.flatnonzero(ok)
    for t in np.unique(chi[idx_ok]):
        pool_by_tod[t] = idx_ok[chi[idx_ok] == t]
    sides = tr.side.values
    for t, cnt in zip(*np.unique(tr.tod_chi.values, return_counts=True)):
        cand = pool_by_tod.get(t)
        if cand is None or len(cand) == 0:
            continue
        pick = rng.choice(cand, size=min(cnt, len(cand)), replace=False)
        s = rng.permutation(sides)[:len(pick)]
        lo[pick[s > 0]] = True
        sh[pick[s < 0]] = True
    return lo, sh


def control(df, I, p, tr, n_draws=300, seed=0, mask=None, order="adverse",
            trail_mode="intrabar", flat_at=None):
    ok = pool_mask(df, I, p, mask)
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_draws):
        lo, sh = draw(df, I, p, tr, ok, rng)
        c = nqs.simulate(df, I, p, lo, sh, order=order, trail_mode=trail_mode,
                         flat_at=flat_at)
        if len(c):
            means.append(c.net_pts.mean())
    return np.array(means)


def score(df, I, p, tr, n_draws=300, seed=0, mask=None, order="adverse",
          trail_mode="intrabar", flat_at=None, label=""):
    if mask is not None:
        tr = tr[np.isin(tr.sig_bar.values, np.flatnonzero(mask))]
    if len(tr) < 25:
        return dict(n=len(tr), note="too few trades")
    mn = control(df, I, p, tr, n_draws, seed, mask, order, trail_mode, flat_at)
    obs = tr.net_pts.mean()
    z = (obs - mn.mean()) / mn.std(ddof=1) if mn.std(ddof=1) > 0 else 0.0
    p_val = float((mn >= obs).mean())
    out = dict(n=len(tr), exp=float(obs), ctrl=float(mn.mean()),
               ctrl_sd=float(mn.std(ddof=1)), excess=float(obs - mn.mean()),
               z=float(z), p=p_val)
    if label:
        print(f"  {label:<40} n={out['n']:>5} exp={out['exp']:>+7.2f} "
              f"ctrl={out['ctrl']:>+7.2f} excess={out['excess']:>+7.2f} "
              f"z={out['z']:>+6.2f} p={out['p']:.4f}")
    return out
