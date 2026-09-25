"""One matched control per strategy, each the control that strategy's own study used.

A generic control cannot be written for these five: the null that a Donchian breakout has to beat
(a random filter of the same selectivity) is not the null a session-fade has to beat (the same
geometry on a random session), and using one for the other is how a control ends up flattering the
thing it tests. So each strategy is scored against the control its own engine already implements,
and only the p-value is compared across them.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t5_adapt as A  # noqa: E402

DRAWS = 1000


def _p(ctl, rule):
    ctl = np.asarray(ctl, float)
    ctl = ctl[np.isfinite(ctl)]
    if not len(ctl):
        return dict(p=np.nan, ctl=np.nan, rule=float(rule))
    return dict(p=float(np.mean(ctl >= rule)), ctl=float(np.median(ctl)), rule=float(rule))


def ftm(feed, block, draws=DRAWS):
    """Random quarter-hour entry on the same sessions, identical management."""
    import ftm_sim as S
    import ftm_backtest as BK
    cnt, t = S.run(verbose=False)
    ts = pd.to_datetime(t["time"])
    td = ts + pd.to_timedelta(np.where(ts.dt.hour >= 18, 1, 0), unit="D")
    sess = (td.dt.year * 10000 + td.dt.month * 100 + td.dt.day).to_numpy()
    cut = A._c("ftm_days", A._ftm_days)["cut"]
    m = sess < cut if block == "research" else sess >= cut
    sub = t[m]
    if len(sub) < 5:
        return dict(p=np.nan, ctl=np.nan, rule=np.nan)
    f = S.load_nq()
    v = BK.control(f, sub, draws=draws)
    return _p(v, sub["R"].mean())


def apm(feed, block, draws=DRAWS):
    """Random eligible fill bar, coin-flip side, identical exits."""
    import apm_core as C
    D = A._c(("apm", feed), lambda: C.load(feed))
    tr, _ = C.run(D, cfg=dict(C.DEFAULT))
    B = C.blocks(D)
    r = C.control(D, tr, dict(C.DEFAULT), B[block], draws=draws, mode="random")
    if r is None:
        return dict(p=np.nan, ctl=np.nan, rule=np.nan)
    return dict(p=r["p"], ctl=r["ctl_median"], rule=r["rule"])


def tfi(feed, block, draws=300):
    """Random bars in the same window and block, same count, same geometry and lock."""
    import tf_design as G
    D = A._c(("tfi", feed), lambda: G.prep(feed))
    cell = A.TFI_CELL
    sm = G.signals(D, cell["N"], cell["adx"], cell["gate"], 1)
    b = D["blocks"][block]
    pnl, sb, xb, why, rk = G.run(D, sm & b, 1, cell["stop"], cell["tp"], cell["exN"])
    if len(pnl) < 5:
        return dict(p=np.nan, ctl=np.nan, rule=np.nan)
    out, _, _ = G.control(D, sm, 1, cell["stop"], cell["tp"], cell["exN"], b, draws=draws)
    return _p(out, (pnl / rk).mean())


def v56(feed, block, draws=2000):
    """A random FILTER of the same selectivity over the same breakout signals."""
    import v56core as K
    P = A._c("v56", A._v56_build)
    cell = A.V56_CELL
    hi = pd.Series(P["h"]).rolling(cell["ent"]).max().shift(1).to_numpy()
    m = np.asarray(P["h"] > hi, bool).copy()
    m[:1000] = False
    m[-(P["max_hold"] + 5):] = False
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0)
    sig = np.flatnonzero(m)
    es = A._v56_pattern(P, cell["k"], cell["w"])[sig]
    xb, rr, _ = K.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sig, P["exit_lo"],
                       cell["stop"], cell["tp"], P["cost"], P["slip"], P["max_hold"], 0)
    blk = (np.arange(P["n"]) < P["cut"]) if block == "research" else (np.arange(P["n"]) >= P["cut"])

    def take(mask):
        free = -1
        keep = []
        for j in np.flatnonzero(mask):
            if sig[j] < free or xb[j] < 0 or not np.isfinite(rr[j]):
                continue
            free = xb[j]
            keep.append(j)
        k = np.asarray(keep, np.int64)
        k = k[blk[sig[k]]] if len(k) else k
        return rr[k] if len(k) else np.zeros(0)

    obs = take(es)
    if len(obs) < 5:
        return dict(p=np.nan, ctl=np.nan, rule=np.nan)
    rate = es.mean()
    rng = np.random.default_rng(53)
    out = np.empty(draws)
    for d in range(draws):
        r = take(rng.random(len(sig)) < rate)
        out[d] = r.mean() if len(r) else np.nan
    return _p(out, obs.mean())


def ibs(feed, block, draws=DRAWS):
    """Random entry sessions from the same block with the same stop, exit rule and hold."""
    import ibs_core as I
    B = A._c(("ibs", feed, 1.0), lambda: A._ibs_build(feed, 1.0))
    masks = I.block_masks(feed, B["date"])
    if block not in masks:
        return dict(p=np.nan, ctl=np.nan, rule=np.nan)
    r = I.matched_control(B, masks[block], A.IBS_CELL, n_draws=draws)
    t = I.cell_trades(B, masks[block], A.IBS_CELL)
    return dict(p=r["p"], ctl=r["ctrl_mean"], rule=float(t["r"].mean()) if len(t) else np.nan)


CONTROLS = {"FTM_ORB": ftm, "APM_VWAP": apm, "TFI": tfi, "V56_CVD": v56, "IBS_SESSION": ibs}
