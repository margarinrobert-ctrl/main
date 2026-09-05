"""Intraday conversion of the Turtle breakout: entries gated to a window, positions closed same day.

WHAT IS BEING CONVERTED. `docs/ib/STUDY_TURTLE.md` measured the Turtle as a MULTI-DAY holder whose
returns come from drift capture rather than from its channel breakout -- a random entry with the
same exits performed as well. The conversion asked for here keeps the breakout TRIGGER and the
ATR-sized risk but replaces everything that made it a position system:

    Turtle (as tested)              intraday scalp (here)
    hold for days                   hard max-hold in minutes, flat by session end
    trailing channel exit           fixed R target, so the trade is decided quickly
    pyramid to 4 units              one unit; sizing creates no edge (CLAUDE.md)
    all hours                       entries only inside a measured window

Because the exit is now a barrier pair rather than a trail, the labelling is the same triple-
barrier machinery the edge lab already validates, and the same conservative intrabar rule applies:
when a bar touches both barriers, it resolves as a STOP. On US30 and NQ that rule can be checked
against TRUE 1-MINUTE PATH data, which is the thing the US100 study could not do.

COSTS are in index points and are broker assumptions -- OHLC bars carry no spread. They are set
relative to each feed's measured ATR so the three instruments are compared on comparable friction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from edgelab import feeds, labels
from edgelab.data import Costs

# Spread/slippage in INDEX POINTS. US30 sits near 31,000 with a 15.6-point 5-minute ATR; US100
# near 12,000 with 14.9; NQ near 20,200 with 11.8. The values below are mid-range retail CFD
# assumptions for the two CFD feeds and the itemised futures cost for NQ, expressed in points.
COSTS = {
    # Gold: a retail XAUUSD CFD spread is roughly 0.20-0.50 USD/oz. 0.30 is a mid assumption and
    # it is LARGE relative to a 5-minute ATR of ~1.2, so the cost floor dominates gold scalping
    # even more than it does the indices. Every sweep prints cost_R next to expectancy.
    "XAUUSD": Costs(spread_rth=0.30, spread_pre=0.45, spread_off=0.70,
                    slip_entry=0.05, slip_stop=0.15, slip_target=0.0),
    "US30":  Costs(spread_rth=2.0, spread_pre=4.0, spread_off=6.0,
                   slip_entry=0.5, slip_stop=1.5, slip_target=0.0),
    "US100": Costs(spread_rth=1.0, spread_pre=2.0, spread_off=3.0,
                   slip_entry=0.25, slip_stop=0.75, slip_target=0.0),
    "NQ":    Costs(spread_rth=0.5, spread_pre=1.0, spread_off=1.5,
                   slip_entry=0.25, slip_stop=0.75, slip_target=0.0, commission=0.72),
}

# Research / validation / production, per instrument. US30 and US100 start in 2016 so they carry
# a genuine three-block split; NQ's file is three years and keeps this branch's 65% session cut.
SPLITS = {"US30":  ("2022-01-01", "2024-01-01"),
          "US100": ("2022-01-01", "2024-01-01")}

# XAUUSD is the PRIMARY instrument and gets a four-way split with a genuinely untouched tail.
#
#   pre-2010 is EXCLUDED entirely: 10.06% zero-range bars and a median 5-minute volume of 14
#   ticks. That is not a market, it is a quote feed idling, and no barrier result computed on it
#   would mean anything.
#
#   research    2010-01-01 -> 2017-12-31   search, features, every parameter choice
#   validation  2018-01-01 -> 2021-12-31   frozen rules only
#   test        2022-01-01 -> 2024-12-31   read after freezing
#   UNTOUCHED   2025-01-01 -> 2026-01-30   READ ONCE, AT THE END, NEVER FED BACK
XAU_SPLIT = dict(start="2010-01-01", research_end="2018-01-01",
                 validation_end="2022-01-01", test_end="2025-01-01")


def blocks(inst, d):
    ix = pd.DatetimeIndex(d["idx"])
    if ix.tz is not None:
        ix = ix.tz_localize(None)
    if inst == "XAUUSD":
        S = XAU_SPLIT
        usable = np.asarray(ix >= pd.Timestamp(S["start"]))
        res = usable & np.asarray(ix < pd.Timestamp(S["research_end"]))
        val = np.asarray((ix >= pd.Timestamp(S["research_end"]))
                         & (ix < pd.Timestamp(S["validation_end"])))
        tst = np.asarray((ix >= pd.Timestamp(S["validation_end"]))
                         & (ix < pd.Timestamp(S["test_end"])))
        unt = np.asarray(ix >= pd.Timestamp(S["test_end"]))
        return dict(research=res, validation=val, test=tst, untouched=unt,
                    oos=val | tst, excluded_pre2010=np.asarray(ix < pd.Timestamp(S["start"])))
    if inst == "NQ":
        from oner_union import _cut
        si, cut, _ = _cut(d)
        r = np.asarray(si < cut)
        return dict(research=r, validation=~r, production=np.zeros(len(r), bool), oos=~r)
    a, b = SPLITS[inst]
    res = np.asarray(ix < pd.Timestamp(a))
    val = np.asarray((ix >= pd.Timestamp(a)) & (ix < pd.Timestamp(b)))
    prod = np.asarray(ix >= pd.Timestamp(b))
    return dict(research=res, validation=val, production=prod, oos=val | prod)


def _rolling_max(x, n):
    return pd.Series(x).rolling(n, min_periods=n).max().to_numpy()


def _rolling_min(x, n):
    return pd.Series(x).rolling(n, min_periods=n).min().to_numpy()


def breakout(d, n):
    """Turtle's own trigger: this bar's high exceeds the previous bar's n-bar highest high."""
    prev = np.roll(_rolling_max(d["h"], n), 1)
    prev[0] = np.nan
    return d["h"] > prev


def breakdown(d, n):
    prev = np.roll(_rolling_min(d["l"], n), 1)
    prev[0] = np.nan
    return d["l"] < prev


def window(d, lo, hi):
    mod = np.asarray(d["mod"], int)
    return (mod >= lo) & (mod < hi) if lo < hi else ((mod >= lo) | (mod < hi))


def label(d, inst, trig, stop_k, rr=1.0, max_hold=20, flat_mod=None, atr=None):
    """Triple-barrier outcome for a set of triggers, in R, net of that instrument's costs."""
    atr = d["atr"] if atr is None else atr
    trig = np.asarray(trig, np.int64)
    return labels.label(d, trig, stop_k * atr[trig], rr=rr, max_hold=max_hold,
                        flat_mod=(flat_mod if flat_mod is not None else 0),
                        costs=COSTS[inst])


def precompute(d, inst, stop_k, rr=1.0, max_hold=20, flat_mod=0, lo=0, hi=1440):
    """Cached outcome for a long entered at EVERY eligible bar in the window."""
    return labels.precompute(d, stop_k, rr=rr, max_hold=max_hold, flat_mod=flat_mod,
                             costs=COSTS[inst], lo=lo, hi=hi)
