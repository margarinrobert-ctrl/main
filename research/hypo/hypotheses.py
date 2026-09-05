"""The hypothesis library. Every entry states a MARKET hypothesis, not just a formula.

The brief is explicit: intraday scalping, trend following, avoid chop, breakout triggers in the
Turtle idiom. So the library stays inside that family and varies the MECHANISM by which chop is
avoided -- because `STUDY_SCALP_TREND.md` and `STUDY_XAUUSD_SCALP.md` between them establish that
an unconditional Donchian breakout is negative gross on gold and fails out of sample on the
indices, while a chop FILTER bolted on afterwards is worth only about +0.05 R.

The distinction this library is built around: a filter EXCLUDES bars after the fact, whereas a
setup REQUIRES a precondition as part of the trigger. H2, H5 and H8 are setups in that sense --
compression, or a level that has already proven itself, is part of what defines the entry rather
than a screen applied to it. That is the untested axis.

Each hypothesis returns (mask, rationale). Masks are causal: every input is known at the close of
the signal bar, and the entry fills on the next one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rmax(x, n):
    return pd.Series(x).rolling(n, min_periods=n).max().to_numpy()


def _rmin(x, n):
    return pd.Series(x).rolling(n, min_periods=n).min().to_numpy()


def _prev(x):
    y = np.roll(x, 1); y[0] = np.nan
    return y


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


# ---------------------------------------------------------------- H1: the Turtle baseline
def h1_donchian(d, n=20):
    """Price makes a new n-bar high, so the prevailing move is extending.

    The classic Turtle trigger and the control for everything else here. Known to be weak; kept
    so every other hypothesis is measured against it rather than against nothing.
    """
    return d["h"] > _prev(_rmax(d["h"], n)), "new n-bar high extends the prevailing move"


# ---------------------------------------------------------------- H2: compression then release
def h2_squeeze(d, n=20, comp_q=0.30, lookback=100):
    """Range COMPRESSION is the precondition, and the break of it is the trade.

    Hypothesis: a market that has just spent n bars in an unusually tight range has stored
    disagreement; when it resolves, the resolution carries. This is the canonical way to avoid
    chop STRUCTURALLY rather than by filtering -- you are not screening out ranges, you are
    requiring one to have just ended. It is also the one Turtle-adjacent idea this branch has not
    tested.
    """
    rng = _rmax(d["h"], n) - _rmin(d["l"], n)
    ref = pd.Series(rng).rolling(lookback, min_periods=lookback // 2).quantile(comp_q).to_numpy()
    was_tight = _prev(rng) <= _prev(ref)
    return (d["h"] > _prev(_rmax(d["h"], n))) & was_tight, \
        "a break out of an unusually tight n-bar range resolves stored disagreement"


# ---------------------------------------------------------------- H3: opening range
def h3_opening_range(d, minutes=30, session_open=570):
    """The opening auction prices overnight information; breaking its range is agreement on direction.

    Hypothesis: the first `minutes` of the cash session establish the day's reference range. A
    break of its high is the point at which participants stop disagreeing about the overnight gap.
    """
    ix = pd.DatetimeIndex(d["idx"])
    if ix.tz is not None:
        ix = ix.tz_localize(None)
    mod = np.asarray(d["mod"], int)
    day = ix.normalize()
    inor = (mod >= session_open) & (mod < session_open + minutes)
    df = pd.DataFrame({"h": d["h"], "l": d["l"], "day": day, "in": inor})
    orh = df[df["in"]].groupby("day")["h"].max().reindex(day).to_numpy()
    live = mod >= session_open + minutes
    prev_close = _prev(d["c"])
    return live & np.isfinite(orh) & (d["h"] > orh) & (prev_close <= orh), \
        "first break of the opening range is the session agreeing on direction"


# ---------------------------------------------------------------- H4: prior-session extreme
def h4_prior_high(d, session_open=570, session_close=960):
    """Prior-session highs hold resting orders; sweeping them creates momentum.

    Hypothesis: a level every participant can see accumulates stops and breakout orders, so the
    sweep is mechanically followed by a burst rather than by drift.
    """
    ix = pd.DatetimeIndex(d["idx"])
    if ix.tz is not None:
        ix = ix.tz_localize(None)
    mod = np.asarray(d["mod"], int)
    day = ix.normalize()
    rth = (mod >= session_open) & (mod < session_close)
    g = pd.DataFrame({"h": d["h"], "day": day})[rth].groupby("day")["h"].max()
    alldays = pd.Index(day.unique()).sort_values()
    pdh = g.reindex(alldays).ffill().shift(1).reindex(day).to_numpy()
    return np.isfinite(pdh) & (d["h"] > pdh) & (_prev(d["c"]) <= pdh), \
        "sweeping the previous session high triggers resting orders"


# ---------------------------------------------------------------- H5: break then retest
def h5_retest(d, n=20, within=6, tol=0.25):
    """Enter on the pullback to a level that has already broken and held.

    Hypothesis: the false-break rate is the breakout's whole problem, and a level that is
    retested and holds has already survived that test. This trades later and less often in
    exchange for a cleaner precondition.
    """
    lvl = _prev(_rmax(d["h"], n))
    broke = d["h"] > lvl
    broke_recent = pd.Series(broke.astype(float)).rolling(within, min_periods=1).max().to_numpy()
    broke_recent = _prev(broke_recent) > 0
    near = np.abs(d["l"] - lvl) <= tol * d["atr"]
    held = d["c"] > lvl
    return broke_recent & near & held, \
        "a broken level retested and held has already survived the false-break test"


# ---------------------------------------------------------------- H6: multi-timeframe alignment
def h6_mtf(d, fast=20, htf_ema=200):
    """Take the intraday break only when the higher-timeframe trend agrees.

    Hypothesis: an intraday breakout against the dominant trend is noise; with it, it is
    continuation. The higher-timeframe reference is an EMA of the SAME series at a long span,
    which is fully closed by construction -- no unfinished higher-timeframe candle is read.
    """
    e = _ema(d["c"], htf_ema)
    slope = e - np.roll(e, 20)
    return (d["h"] > _prev(_rmax(d["h"], fast))) & (d["c"] > e) & (slope > 0), \
        "an intraday break with the dominant trend is continuation, against it is noise"


# ---------------------------------------------------------------- H7: participation-confirmed
def h7_participation(d, n=20, vol_q=0.70, lookback=200):
    """A real break brings participation; a false one is drift on thin activity.

    Hypothesis: the tick count separates a break that institutions are pressing from one that
    leaked through on no interest. Note the activity proxy is a broker TICK COUNT on three of the
    four feeds, not exchange volume.
    """
    v = d["v"]
    ref = pd.Series(v).rolling(lookback, min_periods=lookback // 2).quantile(vol_q).to_numpy()
    return (d["h"] > _prev(_rmax(d["h"], n))) & (v > ref), \
        "a break on above-normal participation is pressed, not leaked"


# ---------------------------------------------------------------- H8: narrow-range expansion
def h8_nr_expansion(d, nr=7, n=10):
    """The narrowest bar in `nr` bars, then a break of the recent high.

    Hypothesis: the NR7 idea -- a single unusually quiet bar marks the pause before expansion.
    A cousin of H2 at a much shorter horizon, included to test whether the compression effect is
    about the RANGE window or about the bar immediately before entry.
    """
    rng = d["h"] - d["l"]
    narrowest = _prev(rng) <= _prev(pd.Series(rng).rolling(nr, min_periods=nr).min().to_numpy())
    return (d["h"] > _prev(_rmax(d["h"], n))) & narrowest, \
        "the narrowest bar in nr marks the pause before expansion"


LIBRARY = {
    "H1 Donchian breakout": h1_donchian,
    "H2 squeeze breakout": h2_squeeze,
    "H3 opening-range break": h3_opening_range,
    "H4 prior-session high": h4_prior_high,
    "H5 break and retest": h5_retest,
    "H6 MTF-aligned break": h6_mtf,
    "H7 participation break": h7_participation,
    "H8 NR expansion": h8_nr_expansion,
}
