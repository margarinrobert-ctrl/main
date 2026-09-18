"""Best risk-adjusted 15-minute configuration inside a fixed 07:00-11:00 New York window.

THE OBJECTIVE IS NOT PROFIT. The request was best Sharpe and smallest drawdown, so configurations
are ranked by Sharpe with a trade-count floor and drawdown reported beside it. That is the right
objective for this problem and it is also the safer one: `STUDY_TURTLE_15M.md` found the unit cap
chosen on return-over-drawdown was the one structural choice that HELD out of sample, while choices
made on raw profit ran off the edge of their grids.

WHAT IS ALREADY KNOWN AND NOT RE-ARGUED. Every session-bound variant of the unconstrained gate was
negative out of sample -- 09:30-16:00 PF 0.90, 06:00-12:00 PF 0.64, against 1.56 with no window --
and the damage was monotone in window length. This search is therefore not expected to recover the
unconstrained result; it is asking a narrower question: given that the position must be flat at
11:00, what is the least-bad risk-adjusted configuration, and does anything in that family survive
the holdout at all?

SEARCH SIZE IS DELIBERATELY SMALL. Two stages, 12 + 108 cells, because a window this narrow leaves
few trades and a large grid would simply find the luckiest corner of a small sample.
"""
from __future__ import annotations

import sys
import itertools
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/turtle15")
import fastbars, mirror, feats, ablate  # noqa: E402

WIN_START, WIN_FLAT = 420, 660          # 07:00 and 11:00 New York


def setup():
    d = fastbars.bars(15)
    _, si, cut = fastbars.sessions(15)
    atr = mirror.wilder_atr(d["h"], d["l"], d["c"], 20)
    C = mirror.channels(d["h"], d["l"])
    F = feats.build(d, atr, C)
    return d, si, cut, atr, C, F


def score(t, sessions_per_year=252.0, n_sessions=None):
    """Sharpe on the per-trade series, annualised by the realised trade rate, plus drawdown."""
    s = ablate.stats(t)
    if s["n"] < 2:
        return dict(**s, sharpe=0.0, sortino=0.0, ret_dd=0.0)
    p = t.pnl.to_numpy()
    per_year = len(p) / max(n_sessions / sessions_per_year, 1e-9) if n_sessions else len(p)
    sd = p.std(ddof=1)
    dn = p[p < 0].std(ddof=1) if (p < 0).sum() > 1 else np.nan
    return dict(**s,
                sharpe=float(p.mean() / sd * np.sqrt(per_year)) if sd > 0 else 0.0,
                sortino=float(p.mean() / dn * np.sqrt(per_year)) if dn and dn > 0 else 0.0,
                ret_dd=float(s["net"] / s["dd"]) if s["dd"] > 0 else 0.0)


def gate(F, adx, dist, vol):
    fin = np.isfinite(F["adx"]) & np.isfinite(F["ema_dist_atr"]) & np.isfinite(F["atr_ratio"])
    return fin & (F["adx"] >= adx) & (F["ema_dist_atr"] >= dist) & (F["atr_ratio"] >= vol)


def window(d):
    mod = d["mod"]
    return (mod >= WIN_START) & (mod < WIN_FLAT - 15)
