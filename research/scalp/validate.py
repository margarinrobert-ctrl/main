"""Validation for an intraday scalp: walk-forward, out-of-sample, Monte Carlo, robustness, ranking.

Two statistics are carried side by side throughout, because on this data they DISAGREE IN SIGN and
each answers a different question:

    expR    trade-weighted mean R. What the account actually earns, because every signal is taken.
    day_R   mean of per-day means. The correct unit of INFERENCE -- intraday triggers cluster
            several to a session, so treating trades as independent overstates significance --
            but it weights a one-trade day equally with a twelve-trade day, so it is NOT the
            economics.

A rule is only interesting when both are positive. Reporting day_R alone would have made several
families here look like edges when their per-trade expectancy is negative.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from edgelab import feeds, fast
from scalp import core


def stats(P, mask, block, days):
    sel = np.flatnonzero(P["valid"] & np.asarray(mask, bool) & np.asarray(block, bool))
    if len(sel) < 20:
        return None
    R = P["R"][sel]
    u, inv = np.unique(days[sel], return_inverse=True)
    per = np.bincount(inv, weights=R) / np.bincount(inv)
    wins, losses = R[R > 0], R[R <= 0]
    eq = np.cumsum(R)
    return dict(n=len(R), days=len(u), win=100.0 * float((R > 0).mean()),
                expR=float(R.mean()), day_R=float(per.mean()), totalR=float(R.sum()),
                pf=float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
                maxdd_R=float(np.max(np.maximum.accumulate(eq) - eq)),
                pos_days=100.0 * float((per > 0).mean()), R=R)


def blocks_table(inst, tf, mask, stop_k, rr, hold, lo, hi, draws=300):
    d = feeds.bars(inst, tf); B = core.blocks(inst, d); days = fast.day_index(d)
    P = core.precompute(d, inst, stop_k, rr=rr, max_hold=hold, flat_mod=hi, lo=lo, hi=hi)
    rows = []
    for name in ("research", "validation", "production", "oos"):
        if name not in B or B[name].sum() == 0:
            continue
        s = stats(P, mask, B[name], days)
        if s is None:
            continue
        c = fast.score_days(P, mask, B[name], days,
                            day_pools=fast._day_pools(P, B[name], days), draws=draws, min_days=15)
        rows.append(dict(block=name, n=s["n"], days=s["days"], win=s["win"], expR=s["expR"],
                         day_R=s["day_R"], pf=s["pf"], maxdd_R=s["maxdd_R"],
                         pos_days=s["pos_days"],
                         ctrl_day_R=(c["ctrl_day_R"] if c else np.nan),
                         exc_day=(c["excess_day_R"] if c else np.nan),
                         p_day=(c["p_day"] if c else np.nan)))
    return pd.DataFrame(rows)


def walk_forward(inst, tf, mask, stop_k, rr, hold, lo, hi, n_folds=6, draws=150):
    d = feeds.bars(inst, tf); days = fast.day_index(d)
    P = core.precompute(d, inst, stop_k, rr=rr, max_hold=hold, flat_mod=hi, lo=lo, hi=hi)
    ix = pd.DatetimeIndex(d["idx"])
    if ix.tz is not None:
        ix = ix.tz_localize(None)
    n = len(d["c"]); edges = np.linspace(0, n, n_folds + 1).astype(int)
    rows = []
    for f in range(n_folds):
        blk = np.zeros(n, bool); blk[edges[f]:edges[f + 1]] = True
        s = stats(P, mask, blk, days)
        if s is None:
            rows.append(dict(fold=f, start=str(ix[edges[f]].date()), n=0))
            continue
        c = fast.score_days(P, mask, blk, days,
                            day_pools=fast._day_pools(P, blk, days), draws=draws, min_days=10)
        rows.append(dict(fold=f, start=str(ix[edges[f]].date()),
                         end=str(ix[edges[f + 1] - 1].date()), n=s["n"], win=s["win"],
                         expR=s["expR"], day_R=s["day_R"],
                         exc_day=(c["excess_day_R"] if c else np.nan)))
    return pd.DataFrame(rows)


def monte_carlo(R, n=20000, seed=5):
    R = np.asarray(R, float)
    if len(R) < 20:
        return None
    rng = np.random.default_rng(seed); m = len(R)
    dds = np.empty(n)
    for i in range(n):
        eq = np.cumsum(rng.permutation(R))
        dds[i] = np.max(np.maximum.accumulate(eq) - eq)
    boot = rng.choice(R, size=(n, m), replace=True)
    means = boot.mean(axis=1)
    return dict(trades=m, median_dd_R=float(np.percentile(dds, 50)),
                p95_dd_R=float(np.percentile(dds, 95)),
                mean_p05=float(np.percentile(means, 5)),
                mean_p50=float(np.percentile(means, 50)),
                mean_p95=float(np.percentile(means, 95)),
                p_edge_negative=float((means <= 0).mean()))


def robustness(inst, tf, mask, stop_k, rr, hold, lo, hi, block="research"):
    """Neighbourhood in geometry. A real edge is a ridge; a fitted one is a spike."""
    d = feeds.bars(inst, tf); B = core.blocks(inst, d); days = fast.day_index(d)
    rows = []
    for s in (stop_k * 0.5, stop_k * 0.75, stop_k, stop_k * 1.5, stop_k * 2.0):
        for r in (rr * 0.5, rr * 0.75, rr, rr * 1.5, rr * 2.0):
            P = core.precompute(d, inst, s, rr=r, max_hold=hold, flat_mod=hi, lo=lo, hi=hi)
            st = stats(P, mask, B[block], days)
            rows.append(dict(stop_atr=round(s, 3), rr=round(r, 3),
                             n=(st["n"] if st else 0),
                             expR=(st["expR"] if st else np.nan),
                             day_R=(st["day_R"] if st else np.nan)))
    return pd.DataFrame(rows)
