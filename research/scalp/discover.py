"""Entry / stop / target / holding discovery for the intraday breakout, with a day-clustered control.

STAGE ORDER, and why. Geometry first (stop, target, hold), because the earlier studies on this
branch showed that a fixed round-turn cost against a small stop dominates every other choice --
there is no point searching entries at a geometry where the cost floor is unreachable. Then the
entry family, then the regime gates, and only then the combined search.

THE NULL is a minute-of-day matched control resampled at the DAY level: intraday triggers cluster
several to a session, so the day is the unit of inference. `edgelab.fast.score_days`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from edgelab import feeds, fast, features as ef
from scalp import core


def eligible(d, P, mask, block):
    return np.flatnonzero(P["valid"] & np.asarray(mask, bool) & np.asarray(block, bool))


def geometry_sweep(inst, tf, lo, hi, entry_n=20, block="research",
                   stops=(0.35, 0.5, 0.75, 1.0, 1.5, 2.0), rrs=(0.75, 1.0, 1.5, 2.0),
                   holds=(6, 12, 20, 40)):
    d = feeds.bars(inst, tf); B = core.blocks(inst, d); blk = B[block]
    sig = core.breakout(d, entry_n) & core.window(d, lo, hi)
    rows = []
    for s in stops:
        for rr in rrs:
            for hold in holds:
                P = core.precompute(d, inst, s, rr=rr, max_hold=hold, flat_mod=hi, lo=lo, hi=hi)
                sel = eligible(d, P, sig, blk)
                if len(sel) < 80:
                    continue
                R = P["R"][sel]
                rows.append(dict(stop_atr=s, rr=rr, hold=hold, n=len(R),
                                 win=100.0 * float((R > 0).mean()), expR=float(R.mean()),
                                 ambig=100.0 * float(P["ambig"][sel].mean()),
                                 cost_R=float(np.median(
                                     (2 * core.COSTS[inst].spread_at(d["mod"])[sel]
                                      + core.COSTS[inst].slip_entry + core.COSTS[inst].slip_stop
                                      + core.COSTS[inst].commission) / (s * d["atr"][sel])))))
    return pd.DataFrame(rows)


def entry_families(d, inst):
    """Breakout variants plus the alternatives the brief names: pullback and continuation."""
    F = ef.build(d)
    fam = {}
    for n in (5, 10, 15, 20, 30, 55):
        fam[f"breakout {n}-bar high"] = core.breakout(d, n)
    hi20 = pd.Series(d["h"]).rolling(20, min_periods=20).max().to_numpy()
    lo10 = pd.Series(d["l"]).rolling(10, min_periods=10).min().to_numpy()
    close = d["c"]; atr = d["atr"]
    fam["pullback: close below EMA20 then reclaim"] = (
        (np.asarray(F["dist_ema20_atr"], float) > 0)
        & (np.roll(np.asarray(F["dist_ema20_atr"], float), 1) < 0))
    fam["continuation: 2 up closes in an uptrend"] = (
        (np.asarray(F["consec_bull"], float) >= 2) & (np.asarray(F["dist_ema50_atr"], float) > 0))
    fam["momentum expansion"] = (np.asarray(F["roc5_atr"], float)
                                 > np.nan_to_num(np.asarray(F["roc5_atr"], float)).std())
    fam["failed breakdown: new 10-bar low then close back up"] = (
        (np.roll(core.breakdown(d, 10), 1)) & (close > np.roll(close, 1)))
    fam["near 20-bar high (within 0.25 ATR)"] = (hi20 - close) < 0.25 * atr
    fam["off the 10-bar low (within 0.5 ATR)"] = (close - lo10) < 0.5 * atr
    return fam, F


def compare_entries(inst, tf, lo, hi, stop_k, rr, hold, block="research", draws=250):
    d = feeds.bars(inst, tf); B = core.blocks(inst, d); blk = B[block]
    days = fast.day_index(d)
    P = core.precompute(d, inst, stop_k, rr=rr, max_hold=hold, flat_mod=hi, lo=lo, hi=hi)
    dp = fast._day_pools(P, blk, days)
    fam, F = entry_families(d, inst)
    W = core.window(d, lo, hi)
    rows = []
    for name, m in fam.items():
        s = fast.score_days(P, m & W, blk, days, day_pools=dp, draws=draws, min_days=20)
        if s:
            s["entry"] = name
            rows.append(s)
    df = pd.DataFrame(rows)
    return df.sort_values("excess_day_R", ascending=False).reset_index(drop=True) if len(df) else df


def gate_search(inst, tf, lo, hi, stop_k, rr, hold, entry_mask, block="research",
                draws=200, qs=(0.25, 0.5, 0.75), min_days=25):
    """Regime / feature gates on top of a fixed entry, scored against the day-clustered control."""
    d = feeds.bars(inst, tf); B = core.blocks(inst, d); blk = B[block]
    days = fast.day_index(d)
    P = core.precompute(d, inst, stop_k, rr=rr, max_hold=hold, flat_mod=hi, lo=lo, hi=hi)
    dp = fast._day_pools(P, blk, days)
    F = ef.build(d)
    W = core.window(d, lo, hi)
    base = entry_mask & W
    rows = []
    for name, arr in F.items():
        if name in ("mod", "bucket15", "bucket30", "min_since_0700", "min_until_1100"):
            continue
        a = np.asarray(arr, float); fin = np.isfinite(a) & blk
        if fin.sum() < 2000:
            continue
        for q in qs:
            t = float(np.quantile(a[fin], q))
            for op, m in ((">", a > t), ("<", a < t)):
                s = fast.score_days(P, base & m & np.isfinite(a), blk, days,
                                    day_pools=dp, draws=draws, min_days=min_days)
                if s:
                    s["gate"] = f"{name}{op}{t:.4g}"
                    rows.append(s)
    df = pd.DataFrame(rows)
    return df.sort_values("excess_day_R", ascending=False).reset_index(drop=True) if len(df) else df
