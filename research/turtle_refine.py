"""Stage 2 of the search: the session window and the gates, for structures that already cohere.

The first sweep held the window fixed at the whole of 07:00-11:00 and varied the geometry.  This
one holds the geometry fixed and varies what the original script calls free: when entries are
allowed inside the window, the ADX ceiling, the distance-above-EMA100 ceiling, how far price must
break through the channel, a hold cap, and whether a session gets more than one attempt.

Two constraints are not negotiable here.  Entries never start before 07:00 or run past 11:00, and
the flatten stays at 11:00 -- that is the brief, not a parameter.  What is being asked is only
whether a NARROWER window inside it does better, which is a fair question: `CLAUDE.md` records
that on this repository's other data, "if trading 07:00-11:00 New York, trade 09:30-11:00" was
worth four times the per-trade result on 44% fewer trades.

Calendar conditions are banned, as they are everywhere else in this repository.  A weekday or
month condition partitions the sample five or twelve ways and hands the search a free lottery;
removing them from an earlier study was worth $8,771 on that holdout.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_search as S
import turtle_sim as T
import turtle_tensor as X
from turtle_sim import P

# 07:00, 07:30, 08:00, 08:30, 09:00, 09:30, 10:00 New York
SESS_START = (420, 450, 480, 510, 540, 570, 600)
SESS_END = (600, 630, 660)
ADX_MAX = (0.0, 18.0, 22.0, 26.0, 30.0)
EXT_MAX = (0.0, 2.0, 3.0, 4.0, 6.0)
MAX_HOLD = (0, 2, 4, 8)
ONE_SHOT = (False, True)
BREAK_TICKS = (0.0, 1.0, 2.0)          # in instrument ticks, resolved per instrument
FLATTEN = 660


def grid_size() -> int:
    return (len([1 for a in SESS_START for b in SESS_END if b > a]) * len(ADX_MAX) * len(EXT_MAX)
            * len(MAX_HOLD) * len(ONE_SHOT) * len(BREAK_TICKS))


def refine(name: str, tf: int, base: P, min_trades: int = 120,
           cost_mult: float = 1.0) -> pd.DataFrame:
    """Sweep the session and gate axes around one fixed geometry, research block only."""
    spec = B.INSTRUMENTS[name]
    full = B.load(name, tf)
    cut = B.split_session(full)
    s = full.window(S.WIN_LO, S.WIN_HI).slice_sessions(0, cut)
    spy = M.SESSIONS_PER_YEAR[name]
    daily = np.zeros(cut)
    out = np.zeros(11)
    minutes = np.unique(s.ny_min)
    mslot = np.searchsorted(minutes, s.ny_min)
    tick = spec["tick"]

    rows = []
    # `max_hold` is the only refined axis that changes the exit tensor, so it is the outer loop.
    for mh in MAX_HOLD:
        b = T.replace(base, max_hold=mh, flatten_min=FLATTEN)
        legs = {e: X.build_leg(s, b, e) for e in {b.exit1, b.exit2}}
        mus = {e: S.bucket_means(s, legs[e], spec, mslot, len(minutes), cost_mult, b.tp_rests)
               for e in legs}
        for ss, se, adx, ext, bt in itertools.product(SESS_START, SESS_END, ADX_MAX, EXT_MAX,
                                                      BREAK_TICKS):
            if se <= ss:
                continue
            p = T.replace(b, sess_start=ss, sess_end=se, adx_max=adx, ext_max=ext,
                          break_ticks=bt * tick)
            t = T.signal_bars(s, p)
            idx = np.flatnonzero(t).astype(np.int64)
            if len(idx) < min_trades:
                continue
            val = t[idx].astype(np.int64)
            h1 = np.bincount(mslot[t == 1], minlength=len(minutes)).astype(float)
            h2 = np.bincount(mslot[t == 2], minlength=len(minutes)).astype(float)
            tot = h1.sum() + h2.sum()
            ctrl = float((h1 @ mus[p.exit1] + h2 @ mus[p.exit2]) / tot) if tot else 0.0
            for osx in ONE_SHOT:
                S._scan_daily(idx, val, s.sess, s.c, legs[p.exit1], legs[p.exit2],
                              p.skip_win, osx, p.side, spec["cost_abs"] * cost_mult,
                              spec["cost_bp"] * cost_mult, spec["stop_slip"] * cost_mult,
                              p.tp_rests, spec.get("comm", 0.0) * cost_mult,
                              spec["point_value"], daily, out)
                if out[0] < min_trades:
                    continue
                st = S._stats(daily, out, spy)
                rows.append({"sess_start": ss, "sess_end": se, "adx_max": adx, "ext_max": ext,
                             "break_ticks": bt, "max_hold": mh, "one_shot": osx, **st,
                             "ctrl_per_trade": ctrl,
                             "ex_per_trade": st["per_trade"] - ctrl,
                             "instrument": name, "tf": tf, "flatten_min": FLATTEN})
    return pd.DataFrame(rows)


def summarise_axis(df: pd.DataFrame, axis: str, metric: str = "sharpe") -> pd.DataFrame:
    """What each level of one axis is worth, averaged over everything else.

    A marginal, not a maximum.  The best cell of a 12,600-cell grid tells you almost nothing about
    which axis carried it; the mean over the other axes tells you whether the axis matters at all,
    and a monotone column is much harder to fake than a single peak.
    """
    g = df.groupby(axis).agg(n_cells=(metric, "size"), median=(metric, "median"),
                             mean=(metric, "mean"), best=(metric, "max"),
                             median_excess=("ex_per_trade", "median"),
                             median_trades=("n", "median"))
    return g


__all__ = ["refine", "summarise_axis", "grid_size", "SESS_START", "SESS_END", "FLATTEN"]
