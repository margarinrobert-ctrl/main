"""Descriptive sweeps on the DISCOVERY block only (brief 8, 17, 18, 20, 29, 41, 42).

Nothing here selects a strategy. These answer the brief's descriptive questions -- when in the
morning does a long actually work, how far do trades run before they resolve, what stop distance
is defensible, how long is it worth holding -- so that later choices are made from measurement
rather than from the round numbers in the brief.

All of it is computed on entries at EVERY eligible bar, so it describes the INSTRUMENT and the
session, not a setup. That is deliberate: it is the baseline any setup has to beat.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import labels
from .data import Costs


def _eval(d, bars_idx, stop_k, rr=1.0, max_hold=16, flat_mod=960, costs=None):
    sp = stop_k * d["atr"][bars_idx]
    return labels.label(d, bars_idx, sp, rr=rr, max_hold=max_hold, flat_mod=flat_mod, costs=costs)


def eligible(d, block, lo=420, hi=660):
    mod = d["mod"]; atr = d["atr"]
    m = block & (mod >= lo) & (mod < hi) & np.isfinite(atr) & (atr > 0)
    m[:300] = False
    return np.flatnonzero(m)


def time_map(d, block, stop_k=1.0, rr=1.0, max_hold=16, bucket=30, lo=420, hi=660):
    """Brief 8 and 29: win rate, expectancy, MFE/MAE and count by time bucket."""
    idx = eligible(d, block, lo, hi)
    r = _eval(d, idx, stop_k, rr, max_hold)
    mod = d["mod"][r["eb"] - 1]                      # the SIGNAL bar's minute of day
    b = (mod // bucket) * bucket
    rows = []
    for bb in np.unique(b):
        m = b == bb
        if m.sum() < 50:
            continue
        R = r["R"][m]
        rows.append(dict(bucket=f"{int(bb)//60:02d}:{int(bb)%60:02d}", n=int(m.sum()),
                         win=100.0 * float((R > 0).mean()), expR=float(R.mean()),
                         pf=float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else np.inf,
                         mfe=float(r["mfe"][m].mean()), mae=float(r["mae"][m].mean()),
                         ambig=100.0 * float(r["ambig"][m].mean())))
    return pd.DataFrame(rows)


def stop_sweep(d, block, ks=(0.35, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5), rr=1.0, max_hold=16):
    """Brief 18: stop distance in ATR units, with the ambiguity cost of each made explicit."""
    idx = eligible(d, block)
    rows = []
    for k in ks:
        r = _eval(d, idx, k, rr, max_hold)
        R = r["R"]
        rows.append(dict(stop_atr=k, n=len(R), win=100.0 * float((R > 0).mean()),
                         expR=float(R.mean()),
                         pf=float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else np.inf,
                         ambig=100.0 * float(r["ambig"].mean()),
                         median_pts=float(np.median(k * d["atr"][idx])),
                         cost_R=_cost_in_R(d, idx, k)))
    return pd.DataFrame(rows)


def _cost_in_R(d, idx, k):
    """How much of one R the round trip consumes, at this stop distance."""
    c = Costs()
    hs = c.spread_at(d["mod"])[idx]
    total = 2.0 * hs + c.slip_entry + c.slip_stop + c.commission
    return float(np.median(total / (k * d["atr"][idx])))


def rr_sweep(d, block, stop_k=1.0, rrs=(0.5, 0.75, 1.0, 1.25, 1.5, 2.0), max_hold=16):
    """Brief 20: is 1R actually the best target, or only the briefed one?"""
    idx = eligible(d, block)
    rows = []
    for rr in rrs:
        r = _eval(d, idx, stop_k, rr, max_hold)
        R = r["R"]
        rows.append(dict(rr=rr, n=len(R), win=100.0 * float((R > 0).mean()), expR=float(R.mean()),
                         pf=float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else np.inf,
                         ambig=100.0 * float(r["ambig"].mean())))
    return pd.DataFrame(rows)


def hold_sweep(d, block, stop_k=1.0, rr=1.0, holds=(2, 4, 6, 8, 12, 16, 24, 32)):
    """Brief 41 and 42: does a maximum holding time help, and where?"""
    idx = eligible(d, block)
    rows = []
    for hgt in holds:
        r = _eval(d, idx, stop_k, rr, hgt)
        R = r["R"]
        rows.append(dict(max_hold_bars=hgt, minutes=hgt * 15, n=len(R),
                         win=100.0 * float((R > 0).mean()), expR=float(R.mean()),
                         pf=float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else np.inf,
                         median_held=float(np.median(r["held"]))))
    return pd.DataFrame(rows)


def excursions(d, block, stop_k=1.0, rr=1.0, max_hold=16):
    """Brief 17 and 19: MFE/MAE distributions, which is what a stop should be sized from."""
    idx = eligible(d, block)
    r = _eval(d, idx, stop_k, rr, max_hold)
    win = r["R"] > 0
    out = {}
    for tag, sel in (("all", np.ones(len(win), bool)), ("winners", win), ("losers", ~win)):
        out[tag] = dict(n=int(sel.sum()),
                        mfe_p50=float(np.percentile(r["mfe"][sel], 50)),
                        mfe_p75=float(np.percentile(r["mfe"][sel], 75)),
                        mfe_p90=float(np.percentile(r["mfe"][sel], 90)),
                        mae_p50=float(np.percentile(r["mae"][sel], 50)),
                        mae_p75=float(np.percentile(r["mae"][sel], 75)),
                        mae_p90=float(np.percentile(r["mae"][sel], 90)),
                        mae_p95=float(np.percentile(r["mae"][sel], 95)))
    return pd.DataFrame(out).T
