"""The clock-anchored range indicator, and breakeven in points with an offset.

Both were added so a TradingView 09:00-range breakout converts without loss:
the script holds the 09:00 high and low for the day, takes only the FIRST
break per side, and moves its stop to entry + 5 after 43 points.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from .conftest import make_bars
from tradingbacktester.core.errors import BacktesterError
from tradingbacktester.core.types import BacktestConfig, ExitReason, ExitSettings
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.indicators.base import REGISTRY
from tradingbacktester.strategy.spec import Compare, Const, Price, StrategySpec

NY = "America/New_York"


def _day_bars(days: int = 2):
    """1-minute bars from 08:50 NY on 4 March 2024, every minute, ``days`` days."""
    start = pd.Timestamp("2024-03-04 08:50", tz=NY).tz_convert("UTC").value
    n = days * 24 * 60
    rng = np.random.default_rng(0)
    close = 1000 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0, 1.0, n)
    low = np.minimum(open_, close) - rng.uniform(0, 1.0, n)
    return make_bars(close, highs=high, lows=low, opens=open_, timeframe="1m",
                     start_ts=start)


PARAMS = {"start": 540, "end": 545, "arm": 568, "last": 960, "timezone": NY}


def _minutes(bars):
    idx = pd.to_datetime(bars.ts, utc=True).tz_convert(NY)
    return (idx.hour * 60 + idx.minute).to_numpy(), idx.normalize()


def test_the_range_is_the_window_high_and_low_held_for_the_day():
    bars = _day_bars()
    out = REGISTRY.compute("TIME_RANGE", bars, PARAMS, "close")
    minute, day = _minutes(bars)
    for d in pd.unique(day):
        on = np.asarray(day == d)
        window = on & (minute >= 540) & (minute < 545)
        if not window.any():
            continue
        hi, lo = bars.high[window].max(), bars.low[window].min()
        after = on & (minute >= 545)
        before = on & (minute < 545)
        assert np.allclose(out["high"][after], hi)
        assert np.allclose(out["low"][after], lo)
        assert np.isnan(out["high"][before]).all()


def test_first_break_is_flagged_once_per_side_per_day_inside_the_arm_window():
    bars = _day_bars()
    out = REGISTRY.compute("TIME_RANGE", bars, PARAMS, "close")
    minute, day = _minutes(bars)
    for d in pd.unique(day):
        on = np.asarray(day == d)
        hits_up = np.flatnonzero(on & (minute >= 568) & (minute < 960)
                                 & (bars.high >= out["high"]))
        flagged = np.flatnonzero(on & (out["first_up"] > 0.5))
        assert list(flagged) == list(hits_up[:1])
        hits_dn = np.flatnonzero(on & (minute >= 568) & (minute < 960)
                                 & (bars.low <= out["low"]))
        assert list(np.flatnonzero(on & (out["first_down"] > 0.5))) == list(hits_dn[:1])
    # a break before the arm minute is not a break
    early = (minute >= 545) & (minute < 568)
    assert not (out["first_up"][early] > 0).any()


def test_the_range_uses_no_future_bar():
    bars = _day_bars()
    out = REGISTRY.compute("TIME_RANGE", bars, PARAMS, "close")
    k = 900
    mangled = make_bars(
        np.concatenate([bars.close[:k + 1], bars.close[k + 1:] * 3]),
        highs=np.concatenate([bars.high[:k + 1], bars.high[k + 1:] * 3]),
        lows=np.concatenate([bars.low[:k + 1], bars.low[k + 1:] * 0.3]),
        opens=bars.open, timeframe="1m", start_ts=int(bars.ts[0]))
    again = REGISTRY.compute("TIME_RANGE", mangled, PARAMS, "close")
    for key in out:
        assert np.array_equal(out[key][:k + 1], again[key][:k + 1], equal_nan=True)


def test_a_range_that_ends_before_it_starts_is_refused():
    with pytest.raises(BacktesterError):
        REGISTRY.compute("TIME_RANGE", _day_bars(1),
                         dict(PARAMS, start=600, end=540), "close")


# --------------------------------------------------------------------------
# Breakeven in points, with a secured offset
# --------------------------------------------------------------------------

def _path():
    """Flat, up 13 points over 13 bars, then straight down."""
    n = 400
    close = np.full(n, 100.0)
    close[200:213] = 100 + np.arange(1, 14) * 1.0
    close[213:260] = 113 - np.arange(1, 48) * 0.8
    open_ = np.concatenate([[close[0]], close[:-1]])
    return make_bars(close, highs=np.maximum(open_, close) + 0.5,
                     lows=np.minimum(open_, close) - 0.5, opens=open_,
                     timeframe="1m")


def _spec(value: float, mode: str, offset: float = 0.0) -> StrategySpec:
    spec = StrategySpec(name="be", indicators=[],
                        entry_long=Compare(Price("close"), ">", Const(100.5)))
    spec.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="points",
                              stop_loss_value=6.0, breakeven_at_r=value,
                              breakeven_mode=mode, breakeven_offset=offset)
    spec.execution.allow_reversal = False
    spec.execution.close_on_opposite_signal = False
    return spec


def _first(spec):
    result = Backtester(_path(), spec, BacktestConfig()).run()
    assert result.trades
    return result.trades[0]


def test_breakeven_in_points_secures_the_offset():
    t = _first(_spec(8.0, "points", offset=2.0))
    assert t.exit_reason is ExitReason.STOP_LOSS
    assert t.exit_price == pytest.approx(t.entry_price + 2.0)


def test_breakeven_offset_zero_is_a_true_breakeven():
    t = _first(_spec(8.0, "points"))
    assert t.exit_price == pytest.approx(t.entry_price)


def test_breakeven_in_points_does_not_arm_short_of_the_distance():
    t = _first(_spec(20.0, "points", offset=2.0))
    assert t.exit_price == pytest.approx(t.entry_price - 6.0)


def test_breakeven_in_r_is_unchanged():
    """1R on a 6-point stop arms at 6 points and moves the stop to entry."""
    t = _first(_spec(1.0, "r"))
    assert t.exit_price == pytest.approx(t.entry_price)
    far = _first(_spec(3.0, "r"))          # 18 points: never reached
    assert far.exit_price == pytest.approx(far.entry_price - 6.0)


def test_breakeven_settings_round_trip_and_old_files_read_as_r():
    spec = _spec(43.0, "points", offset=5.0)
    back = StrategySpec.from_dict(spec.to_dict())
    assert (back.exits.breakeven_mode, back.exits.breakeven_offset) == ("points", 5.0)
    old = spec.to_dict()
    del old["exits"]["breakeven_mode"], old["exits"]["breakeven_offset"]
    loaded = StrategySpec.from_dict(old)
    assert (loaded.exits.breakeven_mode, loaded.exits.breakeven_offset) == ("r", 0.0)
