"""Combining bars into a longer timeframe.

Only upsampling is possible: five 1-minute bars fit exactly inside one 5-minute
bar, but nothing can turn a 5-minute bar back into five 1-minute bars without
inventing prices, so that direction is refused rather than approximated.

Grouping happens in UTC, deliberately.  A 4-hour bar built in local time would
change length twice a year when the clocks move, and a backtest run on it would
quietly disagree with itself across a daylight-saving boundary.  Session-aware
grouping is a strategy concern, handled by session filters at rule level.

The limitation that follows, stated rather than buried: a **daily** bar built
this way runs midnight to midnight UTC, which is not the daily bar a chart or a
data vendor would show for an instrument that trades nearly around the clock --
those are usually cut at the exchange's own daily rollover, 17:00 New York for
CME products.  It does not split the New York cash session, which sits inside a
UTC day in both halves of the year, so an RTH strategy is unaffected; a daily
OHLC for a 24-hour instrument will differ from the vendor's.  Every resampled
series records ``meta["resample_anchor"] = "UTC"`` so the two are never confused
for each other.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from ..core.errors import DataError, InsufficientDataError, TimeframeError
from ..core.timeframe import STANDARD_TIMEFRAMES, Timeframe, TimeframeUnit
from .models import BarSeries

log = logging.getLogger(__name__)

#: Timeframes whose bins are a fixed number of seconds, and can therefore be
#: anchored to the epoch so that the same bar boundaries come out regardless of
#: where the data happens to start.  Days and above are calendar offsets: pandas
#: bins them on the calendar boundary (midnight UTC here) and rejects an origin.
_FIXED_UNITS = (TimeframeUnit.SECOND, TimeframeUnit.MINUTE, TimeframeUnit.HOUR)

_AGGREGATION: dict[str, str] = {
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
}


def available_timeframes(source: Timeframe) -> list[Timeframe]:
    """The standard timeframes that can be built from ``source``.

    Includes ``source`` itself when it is one of the standard set, because
    "leave it alone" is a legitimate choice in the timeframe dropdown.
    """
    if not isinstance(source, Timeframe):
        raise TimeframeError("No source timeframe was given.")
    return [tf for tf in STANDARD_TIMEFRAMES if tf.can_build_from(source)]


def _partial_edges(index: "pd.DatetimeIndex", bars: BarSeries,
                   target: Timeframe) -> tuple[bool, bool]:
    """``(first_is_partial, last_is_partial)`` for the resampled index.

    Judged on **time coverage**, not on how many source bars landed in the
    period: a Sunday with four hours of trading in it is a complete daily bar,
    while a Monday whose file happens to start at 09:00 is not.

    A source bar stamped at ``t`` covers ``[t, t + one source period)``, which
    is the convention every bar in this application follows, so the data covers
    ``[first_ts, last_ts + source_span)``. A target period is complete when
    that interval contains the whole of it.
    """
    if len(index) == 0:
        return False, False
    source = bars.timeframe
    span = int(round(float(source.approx_seconds) * 1e9))
    covered_from = int(bars.ts[0])
    covered_to = int(bars.ts[-1]) + span

    first_start = int(pd.Timestamp(index[0]).value)
    try:
        offset = pd.tseries.frequencies.to_offset(target.pandas_freq)
        last_end = int((pd.Timestamp(index[-1]) + offset).value)
    except (ValueError, TypeError) as exc:      # pragma: no cover - defensive
        log.debug("Could not measure the last period's end (%s); keeping both "
                  "edges rather than dropping a bar on a guess.", exc)
        return False, False
    return covered_from > first_start, covered_to < last_end


def resample(bars: BarSeries, target: Timeframe) -> BarSeries:
    """Combine ``bars`` into ``target`` bars.

    Each output bar takes the first open, the highest high, the lowest low, the
    last close and the total volume of the source bars inside its period, and
    is stamped with the period's **start**.  Periods containing no source bars
    are dropped rather than emitted as gaps, which keeps the no-look-ahead
    guarantee simple: bar ``i`` of the result is always made of bars that
    closed before bar ``i+1`` starts.

    A first or last period the source data only partly covers is dropped for
    the same reason, and ``meta`` records that it was.  Such a bar has the
    wrong open, and a high and low taken from part of the period -- and the
    last one is what every open position is marked to at the end of a run.

    Raises
    ------
    TimeframeError
        If ``target`` is finer than the source, or does not divide into it.
    InsufficientDataError
        If the source is empty.
    """
    if not isinstance(bars, BarSeries):
        raise DataError("There is no dataset to resample.",
                        detail=f"got {type(bars).__name__}")
    if not isinstance(target, Timeframe):
        raise TimeframeError("No target timeframe was given.")
    if bars.is_empty:
        raise InsufficientDataError(
            "This dataset has no bars, so it cannot be converted to another "
            "timeframe.")

    source = bars.timeframe
    if target == source:
        return bars.slice(0, len(bars))
    if not target.can_build_from(source):
        raise TimeframeError(
            f"{target.display_name} bars cannot be built from "
            f"{source.display_name} bars. Bars can only be combined into longer "
            f"ones, and the new length must be a whole multiple of the old one.",
            detail=f"source={source.label} target={target.label}",
        )

    frame = pd.DataFrame(
        {"open": bars.open, "high": bars.high, "low": bars.low,
         "close": bars.close, "volume": bars.volume},
        index=pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True), name="datetime"),
    )
    kwargs: dict[str, Any] = {"label": "left", "closed": "left"}
    if target.unit in _FIXED_UNITS:
        kwargs["origin"] = "epoch"
    try:
        grouped = frame.resample(target.pandas_freq, **kwargs)
        out = grouped.agg(_AGGREGATION)
    except (ValueError, TypeError) as exc:
        raise TimeframeError(
            f"These bars could not be combined into {target.display_name} bars.",
            detail=repr(exc),
        ) from exc

    # An empty period aggregates to NaN prices; so does a period that held only
    # broken rows.  Either way it must not become a bar.
    price_frame = out[["open", "high", "low", "close"]].to_numpy(dtype="float64")
    keep = np.isfinite(price_frame).all(axis=1)
    dropped = int((~keep).sum())
    out = out.loc[keep]
    if out.empty:
        raise InsufficientDataError(
            f"Combining these bars into {target.display_name} bars produced "
            f"nothing usable.",
            detail=f"source_bars={len(bars)} target={target.label}")

    index = pd.DatetimeIndex(out.index).tz_convert("UTC").tz_localize(None)

    # The first and last periods are usually only partly covered by the source
    # data, and a bar that does not represent its whole period is not a bar.
    # On the shipped 5-minute US30 file converted to daily, the first bar's
    # open was the price 90 minutes into the day and its high and low missed
    # that opening move entirely; the last was missing the final three hours.
    # Nothing said so, and the last bar is the one every open position is
    # marked to at the end of a run.
    #
    # This is the same rule the empty-period drop above follows, applied to the
    # edges: emit only periods the data can actually describe. An interior
    # period with few bars is the market being closed, which is a fact about
    # the period rather than a gap in the file, and is kept.
    lead, tail = _partial_edges(index, bars, target)
    if lead or tail:
        stop = len(out) - (1 if tail else 0)
        out = out.iloc[(1 if lead else 0):stop]
        index = index[(1 if lead else 0):stop]
        if out.empty:
            raise InsufficientDataError(
                f"These bars do not cover a single whole "
                f"{target.display_name} period, so combining them would "
                f"produce only partial bars.",
                detail=f"source_bars={len(bars)} target={target.label}")

    ts = index.to_numpy(dtype="datetime64[ns]").astype("int64")
    volume = np.nan_to_num(out["volume"].to_numpy(dtype="float64"), nan=0.0)

    meta = dict(bars.meta)
    meta["resampled_from"] = source.label
    meta["source_bars"] = len(bars)
    # Recorded rather than assumed: a daily bar cut at midnight UTC is not the
    # daily bar a chart or a data vendor would show for an instrument that
    # trades around the clock, and anyone comparing the two needs to know which
    # convention produced these. See the module docstring for why it is UTC.
    meta["resample_anchor"] = "UTC"
    if dropped:
        meta["empty_periods_dropped"] = dropped
    if lead:
        meta["partial_first_period_dropped"] = True
    if tail:
        meta["partial_last_period_dropped"] = True

    result = BarSeries(
        ts=ts,
        open=out["open"].to_numpy(dtype="float64"),
        high=out["high"].to_numpy(dtype="float64"),
        low=out["low"].to_numpy(dtype="float64"),
        close=out["close"].to_numpy(dtype="float64"),
        volume=volume,
        instrument=bars.instrument,
        timeframe=target,
        source=bars.source,
        meta=meta,
    )
    log.info("resampled %s from %s to %s: %d bars -> %d bars",
             bars.instrument.symbol, source.label, target.label, len(bars),
             len(result))
    return result
