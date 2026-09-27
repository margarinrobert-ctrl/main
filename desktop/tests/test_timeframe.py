"""Timeframe parsing, ordering and buildability."""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.errors import TimeframeError
from tradingbacktester.core.timeframe import (STANDARD_TIMEFRAMES, Timeframe,
                                              TimeframeUnit, infer_timeframe)


@pytest.mark.parametrize("text,multiplier,unit", [
    ("1m", 1, TimeframeUnit.MINUTE),
    ("5m", 5, TimeframeUnit.MINUTE),
    ("15min", 15, TimeframeUnit.MINUTE),
    ("30", 30, TimeframeUnit.MINUTE),         # a bare number means minutes
    ("1h", 1, TimeframeUnit.HOUR),
    ("4 hours", 4, TimeframeUnit.HOUR),
    ("D", 1, TimeframeUnit.DAY),
    ("1d", 1, TimeframeUnit.DAY),
    ("daily", 1, TimeframeUnit.DAY),
    ("W", 1, TimeframeUnit.WEEK),
    ("1M", 1, TimeframeUnit.MONTH),           # capital M is month
    ("1m", 1, TimeframeUnit.MINUTE),          # lower m is minute
])
def test_parse(text, multiplier, unit):
    tf = Timeframe.parse(text)
    assert tf.multiplier == multiplier
    assert tf.unit is unit


@pytest.mark.parametrize("bad", ["", "   ", "5 fortnights", "banana", "1y"])
def test_parse_rejects_nonsense(bad):
    with pytest.raises(TimeframeError):
        Timeframe.parse(bad)


def test_zero_multiplier_rejected():
    with pytest.raises(TimeframeError):
        Timeframe(0, TimeframeUnit.MINUTE)


def test_labels():
    assert Timeframe.parse("5m").label == "5m"
    assert Timeframe.parse("1h").label == "1h"
    assert Timeframe.parse("1d").label == "1D"
    assert Timeframe.parse("15m").display_name == "15 minutes"
    assert Timeframe.parse("1h").display_name == "1 hour"


def test_ordering():
    assert Timeframe.parse("1m") < Timeframe.parse("5m")
    assert Timeframe.parse("1h") < Timeframe.parse("1d")
    assert Timeframe.parse("1w") > Timeframe.parse("1d")


def test_can_build_from():
    m1, m5, m15, h1, h4, d1, w1 = (Timeframe.parse(x) for x in
                                   ("1m", "5m", "15m", "1h", "4h", "1d", "1w"))
    assert m5.can_build_from(m1)
    assert m15.can_build_from(m5)
    assert h1.can_build_from(m5)
    assert h4.can_build_from(h1)
    assert d1.can_build_from(h1)
    assert w1.can_build_from(d1)
    assert m5.can_build_from(m5)
    # A finer timeframe cannot be invented from a coarser one.
    assert not m1.can_build_from(m5)
    assert not m5.can_build_from(h1)
    # 15m does not divide into 1h... it does; but 7m does not divide 15m.
    assert not Timeframe.parse("15m").can_build_from(Timeframe.parse("7m"))


def test_pandas_freq():
    assert Timeframe.parse("5m").pandas_freq == "5min"
    assert Timeframe.parse("1h").pandas_freq == "1h"
    assert Timeframe.parse("1d").pandas_freq == "1D"


def test_infer_timeframe():
    ts = np.arange(100, dtype="int64") * 300 * 10 ** 9
    assert infer_timeframe(ts) == Timeframe.parse("5m")
    ts = np.arange(100, dtype="int64") * 86400 * 10 ** 9
    assert infer_timeframe(ts) == Timeframe.parse("1d")


def test_infer_timeframe_is_robust_to_gaps():
    """A weekend gap must not change the inferred timeframe."""
    step = 3600 * 10 ** 9
    ts = list(np.arange(50, dtype="int64") * step)
    ts += [ts[-1] + step * 60]                       # a long break
    ts += [ts[-1] + step * (i + 1) for i in range(50)]
    assert infer_timeframe(np.array(ts, dtype="int64")) == Timeframe.parse("1h")


def test_infer_timeframe_needs_two_bars():
    with pytest.raises(TimeframeError):
        infer_timeframe(np.array([1], dtype="int64"))


def test_standard_timeframes_are_ordered():
    seconds = [tf.approx_seconds for tf in STANDARD_TIMEFRAMES]
    assert seconds == sorted(seconds)
