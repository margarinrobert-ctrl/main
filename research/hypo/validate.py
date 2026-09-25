"""Out-of-sample, walk-forward, parameter plateau, cost stress and Monte Carlo for the leaders.

Nothing here re-optimises. A candidate arrives as (hypothesis, stop, target, hold) already fixed
on the research block, and every function below only measures it somewhere it has not been fitted.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import feeds, fast, labels
from scalp import core
from hypo import hypotheses as H
from hypo.engine import MARKETS, WINDOW, _costs
from hypo.metrics import suite


def _mask_and_P(inst, tf, hyp, stop_k, rr, hold, cost_mult=1.0):
    lo, hi = WINDOW
    d = feeds.bars(inst, tf)
    m, _ = H.LIBRARY[hyp](d)
    m = np.nan_to_num(m).astype(bool) & core.window(d, lo, hi)
    P = labels.precompute(d, stop_k, rr=rr, max_hold=hold, flat_mod=hi,
                          costs=_costs(inst, cost_mult), lo=lo, hi=hi)
    return d, m, P, core.blocks(inst, d), fast.day_index(d)


def blocks_table(hyp, stop_k, rr, hold, cost_mult=1.0):
    rows = []
    for inst, tf in MARKETS:
        d, m, P, B, days = _mask_and_P(inst, tf, hyp, stop_k, rr, hold, cost_mult)
        for bn in ("research", "validation", "test", "untouched", "oos"):
            if bn not in B or B[bn].sum() == 0:
                continue
            sel = np.flatnonzero(P["valid"] & m & B[bn])
            s = suite(P["R"][sel], days[sel], min_trades=25)
            if s is None:
                continue
            s.update(market=inst, block=bn)
            rows.append(s)
    return pd.DataFrame(rows)


def plateau(hyp, stop_k, rr, hold, block="research"):
    """Fraction of the geometry neighbourhood that stays positive, per market and pooled."""
    stops = [stop_k * f for f in (0.5, 0.75, 1.0, 1.5, 2.0)]
    rrs = [rr * f for f in (0.5, 0.75, 1.0, 1.5)]
    rows = []
    for inst, tf in MARKETS:
        for s in stops:
            for r in rrs:
                d, m, P, B, days = _mask_and_P(inst, tf, hyp, s, r, hold)
                sel = np.flatnonzero(P["valid"] & m & B[block])
                st = suite(P["R"][sel], days[sel], min_trades=25)
                rows.append(dict(market=inst, stop_atr=round(s, 2), rr=round(r, 2),
                                 expR=(st["expR"] if st else np.nan)))
    df = pd.DataFrame(rows)
    frac = float((df["expR"] > 0).mean())
    return df, frac


def cost_stress(hyp, stop_k, rr, hold, mults=(0.5, 1.0, 1.5, 2.0), block="research"):
    rows = []
    for mult in mults:
        for inst, tf in MARKETS:
            d, m, P, B, days = _mask_and_P(inst, tf, hyp, stop_k, rr, hold, mult)
            sel = np.flatnonzero(P["valid"] & m & B[block])
            st = suite(P["R"][sel], days[sel], min_trades=25)
            rows.append(dict(cost_mult=mult, market=inst,
                             expR=(st["expR"] if st else np.nan)))
    return pd.DataFrame(rows).pivot(index="cost_mult", columns="market", values="expR")


def monte_carlo(R, n=10000, seed=11, slip_sd=0.02):
    """Permute for the drawdown path; bootstrap for the edge; perturb R for execution noise."""
    R = np.asarray(R, float)
    if len(R) < 25:
        return None
    rng = np.random.default_rng(seed); m = len(R)
    dds = np.empty(n)
    for i in range(n):
        eq = np.cumsum(rng.permutation(R))
        dds[i] = np.max(np.maximum.accumulate(eq) - eq)
    boot = rng.choice(R, size=(n, m), replace=True) - rng.normal(0.0, slip_sd, (n, m))
    means = boot.mean(axis=1)
    return dict(trades=m, median_dd_R=float(np.percentile(dds, 50)),
                p95_dd_R=float(np.percentile(dds, 95)),
                mean_p05=float(np.percentile(means, 5)),
                mean_p50=float(np.percentile(means, 50)),
                p_edge_negative=float((means <= 0).mean()))


def market_returns(hyp, stop_k, rr, hold, block="oos"):
    """Daily R series per market, for portfolio correlation."""
    out = {}
    for inst, tf in MARKETS:
        d, m, P, B, days = _mask_and_P(inst, tf, hyp, stop_k, rr, hold)
        if block not in B:
            continue
        sel = np.flatnonzero(P["valid"] & m & B[block])
        if len(sel) < 25:
            continue
        s = pd.Series(P["R"][sel], index=pd.to_datetime(days[sel], unit="D"))
        out[inst] = s.groupby(level=0).sum()
    return pd.DataFrame(out)
