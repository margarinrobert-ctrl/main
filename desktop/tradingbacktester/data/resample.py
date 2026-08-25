"""Combining bars into a longer timeframe.

Only upsampling is possible: five 1-minute bars fit exactly inside one 5-minute
bar, but nothing can turn a 5-minute bar back into five 1-minute bars without
inventing prices, so that direction is refused rather than approximated.

Grouping happens in UTC, deliberately.  A 4-hour bar built in local time would
change length twice a year when the clocks move, and a backtest run on it would
quietly disagree with itself across a daylight-saving boundary.  Session-aware
grouping is a strategy concern, handled by session filters at rule level.
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


def resample(bars: BarSeries, target: Timeframe) -> BarSeries:
    """Combine ``bars`` into ``target`` bars.

    Each output bar takes the first open, the highest high, the lowest low, the
    last close and the total volume of the source bars inside its period, and
    is stamped with the period's **start**.  Periods containing no source bars
    are dropped rather than emitted as gaps, which keeps the no-look-ahead
    guarantee simple: bar ``i`` of the result is always made of bars that
    closed before bar ``i+1`` starts.

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
    ts = index.to_numpy(dtype="datetime64[ns]").astype("int64")
    volume = np.nan_to_num(out["volume"].to_numpy(dtype="float64"), nan=0.0)

    meta = dict(bars.meta)
    meta["resampled_from"] = source.label
    meta["source_bars"] = len(bars)
    if dropped:
        meta["empty_periods_dropped"] = dropped

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
