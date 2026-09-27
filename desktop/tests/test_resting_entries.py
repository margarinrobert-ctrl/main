"""Resting stop and limit entries: the bracket around a range.

Every test builds bars by hand, so the right answer is known exactly: where
each order fills, which one fills first, what the rest of the fill bar does to
the new position, and when an order stops working.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tradingbacktester.core.errors import StrategyError
from tradingbacktester.core.types import (BacktestConfig, ExecutionSettings,
                                          ExitReason, ExitSettings,
                                          IntrabarPriority, OrderType,
                                          SessionSettings)
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy.spec import (SCHEMA_VERSION, Compare, Const,
                                             ExprOperand, Ind, IndicatorSlot,
                                             Price, SessionWindow, StrategySpec)

from .conftest import make_bars

NY = "America/New_York"


#: Flat bars put in front of every hand-built series, so the rows a test
#: writes start after the strategy's warm-up; bar k of a test is W + k here.
W = 20


def _bars(rows, start="2026-05-04 08:40"):
    """W flat bars, then ``rows`` of (open, high, low, close), one minute apart
    from ``start`` NY -- so the test's own row 0 is 09:00 by default."""
    arr = np.asarray([FLAT] * W + list(rows), dtype="float64")
    start_ts = pd.Timestamp(start, tz=NY).tz_convert("UTC").value
    return make_bars(arr[:, 3], highs=arr[:, 1], lows=arr[:, 2], opens=arr[:, 0],
                     timeframe="1m", start_ts=start_ts)


def _spec(*, place_on: int, up: float, down: float, stop=5.0, target=5.0,
          priority=IntrabarPriority.TRADINGVIEW, kind="stop", bars_live=0,
          cancel=None, oca=True) -> StrategySpec:
    """Place a long order at ``up`` and a short at ``down`` on bar ``place_on``.

    The trigger is "close equals this bar's marker": each test sets the
    marker bar's close to 0.5 above an integer so no other bar matches.
    """
    spec = StrategySpec(name="bracket", indicators=[])
    marker = Compare(Price("close"), "==", Const(float(place_on)))
    spec.entry_long = marker
    spec.entry_short = marker
    spec.entry_long_price = Const(up)
    spec.entry_short_price = Const(down)
    spec.entry_cancel = cancel
    spec.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="points",
                              stop_loss_value=stop, take_profit_enabled=True,
                              take_profit_mode="points", take_profit_value=target)
    spec.execution = ExecutionSettings(intrabar_priority=priority,
                                       allow_reversal=False,
                                       close_on_opposite_signal=False,
                                       entry_order=kind, entry_order_bars=bars_live,
                                       entry_oca=oca)
    spec.session = SessionSettings(enabled=False)
    return spec


def _run(rows, spec, **kw):
    return Backtester(_bars(rows, **kw), spec, BacktestConfig()).run()


# Bar 1 closes at exactly 1.0, the marker; the range is 95-105 everywhere else.
FLAT = (100.0, 101.0, 99.0, 100.2)
MARK = (100.0, 101.0, 99.0, 1.0)


def test_a_buy_stop_fills_at_its_level_and_the_short_is_cancelled():
    rows = [FLAT, MARK, FLAT, (100.0, 104.0, 99.5, 103.0), FLAT, FLAT,
            (100.0, 100.5, 90.0, 92.0), FLAT, FLAT, (100.0, 110.0, 99.0, 108)]
    # A long stop at 102 and a short stop at 97.  Bar 3 trades to 104: the long
    # fills at 102. Bar 6 falls to 90, through the short's level, but OCA has
    # already cancelled it -- and through the long's stop at 97.
    result = _run(rows, _spec(place_on=1, up=102.0, down=97.0))
    assert len(result.trades) == 1
    t = result.trades[0]
    assert t.side.value == "long"
    assert (t.entry_bar - W, t.entry_price) == (3, 102.0)
    assert (t.exit_bar - W, t.exit_price, t.exit_reason) == (6, 97.0, ExitReason.STOP_LOSS)
    assert result.orders[0].order_type is OrderType.STOP
    assert result.orders[0].stop_price == 102.0


def test_a_bar_that_opens_through_the_stop_fills_at_the_open():
    rows = [FLAT, MARK, (104.0, 105.0, 103.5, 104.5), FLAT, FLAT]
    t = _run(rows, _spec(place_on=1, up=102.0, down=97.0, target=50, stop=50)).trades[0]
    assert (t.entry_bar - W, t.entry_price) == (2, 104.0)


def test_the_rest_of_the_fill_bar_can_hit_the_target():
    # Open nearer the low, so TradingView's path is O -> L -> H -> C: the bar
    # dips, rises through the 102 stop, runs on to 108 (target 107), closes.
    rows = [FLAT, MARK, (100.0, 108.0, 99.8, 106.0), FLAT]
    t = _run(rows, _spec(place_on=1, up=102.0, down=90.0)).trades[0]
    assert (t.entry_bar - W, t.entry_price) == (2, 102.0)
    assert (t.exit_bar - W, t.exit_price, t.exit_reason) == (2, 107.0, ExitReason.TAKE_PROFIT)


def test_the_part_of_the_fill_bar_before_the_fill_cannot_stop_it_out():
    # Open 97.5 is nearer the low (96) than the high (103), so the path is
    # O -> L -> H -> C: the dip below the would-be stop (97) comes BEFORE the
    # fill at 102 on the way up, and the trade survives the bar.
    rows = [FLAT, MARK, (97.5, 103.0, 96.0, 102.5), FLAT, FLAT]
    result = _run(rows, _spec(place_on=1, up=102.0, down=90.0, stop=5, target=50))
    t = result.trades[0]
    assert t.entry_bar - W == 2
    assert t.exit_bar - W != 2


def test_after_the_fill_the_path_decides_between_stop_and_target():
    # Open nearer the high: O -> H -> L -> C. Up through 102 (fill), on to 104,
    # then down to 95: the stop at 97 is reached; the 107 target never was.
    rows = [FLAT, MARK, (100.0, 104.0, 95.0, 96.0), FLAT]
    t = _run(rows, _spec(place_on=1, up=102.0, down=90.0)).trades[0]
    assert (t.exit_bar - W, t.exit_price, t.exit_reason) == (2, 97.0, ExitReason.STOP_LOSS)


def test_both_sides_on_one_bar_follow_the_path():
    # Open 100.8 is nearer the high (101.x): O -> H -> L. The high reaches the
    # 101.5 buy stop first, so the long fills and OCA cancels the short.
    near_high = [FLAT, MARK, (100.8, 106.0, 94.0, 99.0), FLAT]
    first = _run(near_high, _spec(place_on=1, up=101.5, down=98.5, stop=50,
                                  target=50)).trades[0]
    assert first.side.value == "long"
    near_low = [FLAT, MARK, (99.2, 106.0, 94.0, 99.0), FLAT]
    first = _run(near_low, _spec(place_on=1, up=101.5, down=98.5, stop=50,
                                 target=50)).trades[0]
    assert first.side.value == "short"


def test_without_oca_the_other_side_stays_working():
    rows = [FLAT, MARK, (100.0, 104.0, 99.5, 103.0), (103.0, 110.0, 102.5, 109.0),
            FLAT, (100.0, 100.5, 90.0, 91.0), FLAT]
    result = _run(rows, _spec(place_on=1, up=102.0, down=97.0, oca=False))
    assert [t.side.value for t in result.trades] == ["long", "short"]


def test_a_cancel_rule_stops_the_orders_at_that_bars_close():
    rows = [FLAT, MARK, FLAT, FLAT, (100.0, 104.0, 99.5, 103.0), FLAT]
    cancel = SessionWindow("09:03", "23:59:59", NY, (0, 1, 2, 3, 4, 5, 6))
    # Cancelled at the close of the 09:03 bar (row 3); the break is row 4.
    assert _run(rows, _spec(place_on=1, up=102.0, down=97.0, cancel=cancel)).trades == []
    # The bar that cancels still fills if it trades through first.
    rows[3] = (100.0, 104.0, 99.5, 103.0)
    assert len(_run(rows, _spec(place_on=1, up=102.0, down=97.0,
                                cancel=cancel)).trades) == 1


def test_orders_expire_after_their_bar_count():
    rows = [FLAT, MARK, FLAT, FLAT, (100.0, 104.0, 99.5, 103.0), FLAT]
    assert _run(rows, _spec(place_on=1, up=102.0, down=97.0, bars_live=2)).trades == []
    assert len(_run(rows, _spec(place_on=1, up=102.0, down=97.0,
                                bars_live=3)).trades) == 1


def test_orders_do_not_survive_the_day():
    # Day orders end at the INSTRUMENT's midnight. The test instrument keeps
    # UTC, and 4 May 2026 is on New York daylight time (UTC-4), so starting at
    # 19:37 New York puts row 3 at 00:00 UTC on the next day.
    rows = [FLAT, MARK] + [FLAT] * 2 + [(100.0, 104.0, 99.5, 103.0)]
    bars = _bars(rows, start="2026-05-04 19:37")
    result = Backtester(bars, _spec(place_on=1, up=102.0, down=97.0),
                        BacktestConfig()).run()
    assert result.trades == []


def test_limit_entries_fill_on_the_retrace():
    rows = [FLAT, MARK, FLAT, (100.0, 100.5, 97.5, 99.0), FLAT, FLAT]
    t = _run(rows, _spec(place_on=1, up=98.0, down=110.0, kind="limit",
                         stop=50, target=50)).trades[0]
    assert (t.side.value, t.entry_bar - W, t.entry_price) == ("long", 3, 98.0)


def test_market_strategies_are_untouched():
    rows = [FLAT, MARK, FLAT, (100.0, 104.0, 99.5, 103.0), FLAT]
    spec = _spec(place_on=1, up=102.0, down=97.0)
    spec.execution.entry_order = "market"
    spec.entry_short = None
    t = _run(rows, spec).trades[0]
    assert (t.entry_bar - W, t.entry_price) == (2, FLAT[0])


# --------------------------------------------------------------------------
# The strategy file
# --------------------------------------------------------------------------

def test_resting_fields_round_trip_and_mark_the_file_format_two():
    spec = _spec(place_on=1, up=102.0, down=97.0,
                 cancel=SessionWindow("10:29", "23:59:59", NY))
    spec.entry_long_price = ExprOperand("+", Price("high"), Const(10.0))
    d = spec.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION == 2
    back = StrategySpec.from_dict(json.loads(json.dumps(d)))
    assert back.execution.entry_order == "stop"
    assert back.entry_long_price.to_dict() == spec.entry_long_price.to_dict()
    assert back.entry_cancel.to_dict() == spec.entry_cancel.to_dict()
    plain = StrategySpec(name="plain", entry_long=Compare(Price("close"), ">", Const(1)))
    assert plain.to_dict()["schema_version"] == 1


def test_a_newer_format_is_refused_not_misread():
    d = _spec(place_on=1, up=1, down=0).to_dict()
    d["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(StrategyError):
        StrategySpec.from_dict(d)


def test_a_stop_entry_needs_a_price():
    spec = _spec(place_on=1, up=102.0, down=97.0)
    spec.entry_short_price = None
    with pytest.raises(StrategyError) as exc:
        spec.validate()
    assert "entry_short_price" in str(exc.value)


def test_combining_refuses_resting_entry_strategies():
    from tradingbacktester.strategy.combine import combine_strategies
    a = _spec(place_on=1, up=102.0, down=97.0)
    b = StrategySpec(name="b", entry_long=Compare(Price("close"), ">", Const(1)))
    with pytest.raises(StrategyError) as exc:
        combine_strategies([a, b])
    assert "resting" in str(exc.value)


def test_saving_from_the_panel_keeps_what_the_panel_does_not_show(qapp):
    """The window used to replace whole settings blocks on save, which would
    reset stop entries to market orders and drop partial-exit ladders."""
    from tradingbacktester.ui.widgets.risk_panel import (RiskPanel,
                                                         fold_panel_into_spec)
    spec = _spec(place_on=1, up=102.0, down=97.0)
    spec.exits.partial_exits = ((0.5, 1.0),)
    panel = RiskPanel()
    panel.apply_config(BacktestConfig(execution=spec.execution, exits=spec.exits))
    config = panel.build_config()
    fold_panel_into_spec(spec, config, panel.shown_fields)
    assert spec.execution.entry_order == "stop"
    assert spec.execution.intrabar_priority is IntrabarPriority.TRADINGVIEW
    assert spec.exits.partial_exits == ((0.5, 1.0),)
    assert spec.exits.stop_loss_value == 5.0


# --------------------------------------------------------------------------
# The range locked at the close of the bar that completes it
# --------------------------------------------------------------------------

def test_the_range_can_be_ready_at_the_close_of_its_last_bar():
    from tradingbacktester.indicators.base import REGISTRY
    rows = [(100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(40)]
    arr = np.asarray(rows)
    bars = make_bars(arr[:, 3], highs=arr[:, 1], lows=arr[:, 2], opens=arr[:, 0],
                     timeframe="1m", start_ts=pd.Timestamp(
                         "2026-05-04 09:00", tz=NY).tz_convert("UTC").value)
    params = {"start": 540, "end": 570, "arm": 570, "last": 630,
              "timezone": NY, "ready": "bar_close"}
    out = REGISTRY.compute("TIME_RANGE", bars, params, "close")
    assert np.flatnonzero(out["lock"] > 0.5).tolist() == [29]       # the 09:29 bar
    assert np.isnan(out["high"][28])
    assert out["high"][29] == max(r[1] for r in rows[:30])
    assert out["low"][29] == min(r[2] for r in rows[:30])
    later = REGISTRY.compute("TIME_RANGE", bars, dict(params, ready="next_bar"), "close")
    assert np.flatnonzero(later["lock"] > 0.5).tolist() == [30]



def test_no_lock_on_a_day_whose_completing_bar_is_missing():
    """A script that locks on `time_close == rangeEnd` has no lock when the
    09:29 bar is absent; the levels still exist from 09:30 for anything else."""
    from tradingbacktester.indicators.base import REGISTRY
    rows = [(100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(40)]
    arr = np.delete(np.asarray(rows), 29, axis=0)          # drop 09:29
    start = pd.Timestamp("2026-05-04 09:00", tz=NY).tz_convert("UTC").value
    ts = start + np.delete(np.arange(40), 29) * 60_000_000_000
    bars = make_bars(arr[:, 3], highs=arr[:, 1], lows=arr[:, 2], opens=arr[:, 0],
                     timeframe="1m")
    bars.ts = ts.astype("int64")
    out = REGISTRY.compute("TIME_RANGE", bars, {
        "start": 540, "end": 570, "arm": 570, "last": 630, "timezone": NY,
        "ready": "bar_close"}, "close")
    assert not (out["lock"] > 0.5).any()
    assert out["high"][29] == max(r[1] for r in rows[:29])    # the 09:30 bar
