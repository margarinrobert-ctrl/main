"""Run every hypothesis across every market and geometry, on the research block only.

COMPUTE ORDER MATTERS. The outcome of a trade depends only on its signal bar and the geometry, so
the expensive object -- the barrier walk -- is computed once per (market, geometry) and every
hypothesis is then an index into it. That turns 768 backtests into 96 walks plus indexing.

NO MARKET IS OPTIMISED FOR. Each hypothesis is scored on all four independently and the ranking
rewards agreement across them; a rule that only works on one market is explicitly penalised by the
robustness score rather than quietly winning on its best market.
"""
from __future__ import annotations

import itertools
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import feeds, fast, labels
from edgelab.data import Costs
from scalp import core
from hypo import hypotheses as H
from hypo.metrics import suite

MARKETS = [("US30", 5), ("US100", 15), ("NQ", 5), ("XAUUSD", 5)]
WINDOW = (540, 780)                       # 09:00-13:00 New York, the window every study points at
GEOMS = list(itertools.product((1.0, 1.5, 2.0, 3.0), (1.0, 1.5, 2.0), (12, 24)))


def _costs(inst, mult=1.0):
    c = core.COSTS[inst]
    return Costs(spread_rth=c.spread_rth * mult, spread_pre=c.spread_pre * mult,
                 spread_off=c.spread_off * mult, slip_entry=c.slip_entry * mult,
                 slip_stop=c.slip_stop * mult, slip_target=c.slip_target,
                 commission=c.commission * mult)


def run_market(inst, tf, block="research", cost_mult=1.0, geoms=None, verbose=True):
    lo, hi = WINDOW
    d = feeds.bars(inst, tf)
    B = core.blocks(inst, d)
    if block not in B:
        return pd.DataFrame()
    blk = B[block]
    days = fast.day_index(d)
    W = core.window(d, lo, hi)
    masks = {}
    for name, fn in H.LIBRARY.items():
        m, why = fn(d)
        masks[name] = (np.nan_to_num(m).astype(bool) & W, why)
    rows = []
    for stop_k, rr, hold in (geoms or GEOMS):
        P = labels.precompute(d, stop_k, rr=rr, max_hold=hold, flat_mod=hi,
                              costs=_costs(inst, cost_mult), lo=lo, hi=hi)
        for name, (m, why) in masks.items():
            sel = np.flatnonzero(P["valid"] & m & blk)
            if len(sel) < 30:
                continue
            s = suite(P["R"][sel], days[sel])
            if s is None:
                continue
            s.update(hypothesis=name, market=inst, tf=tf, stop_atr=stop_k, rr=rr,
                     hold=hold, block=block, cost_mult=cost_mult,
                     ambig=100.0 * float(P["ambig"][sel].mean()))
            rows.append(s)
    df = pd.DataFrame(rows)
    if verbose:
        print(f"  {inst} {tf}m {block}: {len(df)} hypothesis x geometry results", flush=True)
    return df


def run_all(block="research", cost_mult=1.0, geoms=None, verbose=True):
    out = [run_market(i, t, block, cost_mult, geoms, verbose) for i, t in MARKETS]
    return pd.concat([x for x in out if len(x)], ignore_index=True)


def cross_market(df, min_markets=4, min_trades=60):
    """Collapse to hypothesis x geometry, keeping only cells present on every market.

    The aggregate is the MEDIAN across markets, not the mean: one spectacular market should not
    carry a cell, and the median makes that explicit.
    """
    d = df[df["n"] >= min_trades]
    g = d.groupby(["hypothesis", "stop_atr", "rr", "hold"])
    rows = []
    for key, sub in g:
        if sub["market"].nunique() < min_markets:
            continue
        rows.append(dict(hypothesis=key[0], stop_atr=key[1], rr=key[2], hold=key[3],
                         markets=sub["market"].nunique(),
                         n=int(sub["n"].sum()),
                         med_expR=float(sub["expR"].median()),
                         min_expR=float(sub["expR"].min()),
                         med_pf=float(sub["pf"].median()),
                         med_sharpe=float(sub["sharpe"].median()),
                         med_sortino=float(sub["sortino"].median()),
                         med_win=float(sub["win"].median()),
                         worst_dd=float(sub["maxdd_R"].max()),
                         med_calmar=float(sub["calmar"].median()),
                         positive_markets=int((sub["expR"] > 0).sum())))
    r = pd.DataFrame(rows)
    return r.sort_values(["positive_markets", "med_expR"], ascending=False).reset_index(drop=True) \
        if len(r) else r
