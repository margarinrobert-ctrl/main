"""Splicing futures contracts into one continuous series.

The test that matters is the first one: across a roll, the series must report
the move the market made and not the carry gap between two contracts. Everything
else here exists to stop that one being right by accident.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.errors import DataError, InsufficientDataError
from tradingbacktester.core.timeframe import Timeframe
from tradingbacktester.data.continuous import (DEFAULT_ROLL_DAYS,
                                               VOLUME_CONFIRM_BARS,
                                               Adjustment, Contract, RollRule,
                                               build_continuous, describe)
from tradingbacktester.data.instruments import default_instrument_for
from tradingbacktester.data.models import BarSeries

_HOUR = 3_600_000_000_000
_START = 1_672_617_600_000_000_000


def _series(n: int, first_close: float, *, start_index: int = 0,
            step: float = 1.0, volume: float = 1000.0,
            symbol: str = "NQ", timeframe: str = "1h") -> BarSeries:
    """A straight ramp, so any distortion at a join is visible immediately."""
    closes = first_close + np.arange(n, dtype="float64") * step
    ts = _START + (np.arange(n, dtype="int64") + start_index) * _HOUR
    return BarSeries(
        ts=ts, open=closes - 0.5, high=closes + 1.0, low=closes - 1.0,
        close=closes, volume=np.full(n, float(volume)),
        instrument=default_instrument_for(symbol),
        timeframe=Timeframe.parse(timeframe), source="unit-test", meta={})


def _pair(gap: float = 40.0, overlap: int = 20):
    """Two contracts, the second ``gap`` higher, overlapping by ``overlap``."""
    front = _series(100, 100.0)
    nxt = _series(100, 100.0 + (100 - overlap) * 1.0 + gap,
                  start_index=100 - overlap)
    return front, nxt


# --------------------------------------------------------------------------
# The point of the whole module
# --------------------------------------------------------------------------

def test_an_adjusted_join_reports_the_market_move_not_the_carry_gap():
    front, nxt = _pair(gap=40.0)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.BACK_ADJUSTED,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    ts = out.bars.ts
    at = out.rolls[0].at_ts
    i = int(np.searchsorted(ts, at))
    step = float(out.bars.close[i + 1] - out.bars.close[i])
    # The underlying ramps by 1.0 a bar. The 40-point gap is carry, not a move.
    assert step == pytest.approx(1.0)


def test_an_unadjusted_join_carries_the_gap_and_says_so():
    front, nxt = _pair(gap=40.0)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.UNADJUSTED,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    ts = out.bars.ts
    i = int(np.searchsorted(ts, out.rolls[0].at_ts))
    step = float(out.bars.close[i + 1] - out.bars.close[i])
    assert step == pytest.approx(41.0)          # 1.0 of move plus 40.0 of gap
    text = describe(out, "USD")
    assert "really traded" in text
    assert "wrong by that much" in text


def test_ratio_adjustment_keeps_percentage_returns_and_positive_prices():
    front, nxt = _pair(gap=40.0)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.RATIO,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    assert float(out.bars.low.min()) > 0
    ts = out.bars.ts
    at = out.rolls[0].at_ts
    i = int(np.searchsorted(ts, at))
    # The proportional move across the join is the next contract's own, not one
    # manufactured by the difference between two contracts' price levels.
    j = int(np.searchsorted(nxt.ts, at))
    assert (float(out.bars.close[i + 1]) / float(out.bars.close[i])
            == pytest.approx(float(nxt.close[j + 1]) / float(nxt.close[j])))


def test_the_front_contract_keeps_its_real_prices():
    """Adjustment moves history onto the newest contract, never the reverse."""
    front, nxt = _pair(gap=40.0)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.BACK_ADJUSTED,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    assert float(out.bars.close[-1]) == pytest.approx(float(nxt.close[-1]))


# --------------------------------------------------------------------------
# The spliced series has to be a series the engine will run on
# --------------------------------------------------------------------------

@pytest.mark.parametrize("adjustment", list(Adjustment))
def test_the_result_is_strictly_ascending_with_no_duplicate_bar(adjustment):
    """The engine refuses a repeated timestamp, and a roll is where one appears."""
    front, nxt = _pair()
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=adjustment,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    assert np.all(np.diff(out.bars.ts) > 0)
    assert len(out.bars) == len(set(out.bars.ts.tolist()))


def test_the_roll_bar_is_supplied_once_by_the_contract_handing_over():
    front, nxt = _pair(overlap=20)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.UNADJUSTED,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    at = out.rolls[0].at_ts
    i = int(np.searchsorted(out.bars.ts, at))
    assert float(out.bars.close[i]) == pytest.approx(float(front.close[-1]))


def test_three_contracts_splice_end_to_end():
    a = _series(100, 100.0)
    b = _series(100, 180.0, start_index=80)
    c = _series(100, 260.0, start_index=160)
    out = build_continuous([Contract("H", a), Contract("M", b), Contract("U", c)],
                           adjustment=Adjustment.BACK_ADJUSTED,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    assert len(out.rolls) == 2
    assert out.contracts == ["H", "M", "U"]
    assert np.all(np.diff(out.bars.ts) > 0)


# --------------------------------------------------------------------------
# Choosing the roll
# --------------------------------------------------------------------------

def test_the_volume_rule_rolls_where_the_next_contract_takes_over():
    front = _series(100, 100.0, volume=1000.0)
    nxt = _series(100, 180.0, start_index=60, volume=100.0)
    # From the 20th overlapping bar the back month trades more.
    nxt.volume[20:] = 5000.0
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.VOLUME)
    # Confirmed over VOLUME_CONFIRM_BARS, so the roll is at the last bar of the
    # first confirming run -- not the first bar the back month happened to win.
    expected = int(front.ts[60 + 20])
    assert out.rolls[0].at_ts == expected
    assert "volume crossover" in out.rolls[0].rule


def test_one_busy_bar_in_the_back_month_does_not_roll_the_series():
    front = _series(100, 100.0, volume=1000.0)
    nxt = _series(100, 180.0, start_index=60, volume=100.0)
    nxt.volume[5] = 9999.0                  # a single print, not a handover
    nxt.volume[25:] = 5000.0
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.VOLUME)
    assert out.rolls[0].at_ts == int(front.ts[60 + 25])


def test_a_volume_crossover_that_never_happens_falls_back_and_says_so():
    front = _series(100, 100.0, volume=5000.0)
    nxt = _series(100, 180.0, start_index=60, volume=10.0)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.VOLUME, days_before_end=1)
    assert "never happened" in out.rolls[0].rule
    assert out.rolls[0].at_ts < int(front.ts[-1])


def test_days_before_end_rolls_that_many_days_early():
    front = _series(100, 100.0)             # 100 hourly bars, just over 4 days
    nxt = _series(100, 180.0, start_index=40)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=1)
    assert out.rolls[0].at_ts <= int(front.ts[-1]) - 24 * _HOUR
    assert "1 days before" in out.rolls[0].rule


def test_the_last_bar_rule_rolls_on_the_last_bar():
    front, nxt = _pair(overlap=20)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.LAST_BAR)
    assert out.rolls[0].at_ts == int(front.ts[-1])


def test_a_roll_the_next_contract_cannot_take_over_from_moves_back():
    """The roll bar must exist in both series or the join leaves a hole.

    A back month that has not started trading every bar yet is the usual cause:
    the roll rule picks a bar, and that contract simply has no print on it.
    """
    front = _series(100, 100.0)
    full = _series(100, 180.0, start_index=40)
    # The back month trades only every third bar until well past the roll.
    thin = np.concatenate([np.arange(0, 40, 3), np.arange(40, 100)])
    nxt = BarSeries(ts=full.ts[thin], open=full.open[thin],
                    high=full.high[thin], low=full.low[thin],
                    close=full.close[thin], volume=full.volume[thin],
                    instrument=full.instrument, timeframe=full.timeframe,
                    source=full.source, meta={})
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=2)
    assert out.rolls[0].at_ts in set(nxt.ts.tolist())
    assert "moved back" in out.rolls[0].rule
    assert np.all(np.diff(out.bars.ts) > 0)


def test_a_roll_chosen_before_the_overlap_moves_forward_into_it():
    """A days-before-expiry roll can fall before the back month started.

    Walking only backwards from the chosen bar then finds nothing and refuses
    two contracts that plainly do overlap. The roll has to be clamped INTO the
    overlap, in whichever direction it fell outside it.
    """
    front = _series(400, 100.0)                 # ~16 days of hourly bars
    nxt = _series(200, 500.0, start_index=380)  # overlaps only the last twenty
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=10)
    assert out.rolls[0].at_ts == int(nxt.ts[0])
    assert "moved forward" in out.rolls[0].rule
    assert np.all(np.diff(out.bars.ts) > 0)


def test_a_roll_chosen_after_the_overlap_moves_back_into_it():
    front = _series(200, 100.0)
    nxt = _series(200, 500.0, start_index=100)
    # The back month stops trading before the front one does.
    nxt = BarSeries(ts=nxt.ts[:60], open=nxt.open[:60], high=nxt.high[:60],
                    low=nxt.low[:60], close=nxt.close[:60],
                    volume=nxt.volume[:60], instrument=nxt.instrument,
                    timeframe=nxt.timeframe, source=nxt.source, meta={})
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           rule=RollRule.LAST_BAR)
    assert out.rolls[0].at_ts == int(nxt.ts[-1])
    assert "moved back to the last bar" in out.rolls[0].rule
    assert np.all(np.diff(out.bars.ts) > 0)


# --------------------------------------------------------------------------
# What it refuses
# --------------------------------------------------------------------------

def test_one_contract_is_refused():
    with pytest.raises(InsufficientDataError):
        build_continuous([Contract("H", _series(50, 100.0))])


def test_contracts_that_never_overlap_are_refused():
    front = _series(50, 100.0)
    nxt = _series(50, 180.0, start_index=200)
    with pytest.raises(DataError) as exc:
        build_continuous([Contract("H", front), Contract("M", nxt)],
                         rule=RollRule.LAST_BAR)
    assert "no bar in common" in str(exc.value)


def test_mixed_bar_sizes_are_refused():
    front = _series(50, 100.0, timeframe="1h")
    nxt = _series(50, 180.0, start_index=40, timeframe="4h")
    with pytest.raises(DataError) as exc:
        build_continuous([Contract("H", front), Contract("M", nxt)])
    assert "bar size" in str(exc.value)


def test_mixed_instruments_are_refused():
    front = _series(50, 100.0, symbol="NQ")
    nxt = _series(50, 180.0, start_index=40, symbol="ES")
    with pytest.raises(DataError) as exc:
        build_continuous([Contract("H", front), Contract("M", nxt)])
    assert "one instrument" in str(exc.value)


# --------------------------------------------------------------------------
# Saying what it did
# --------------------------------------------------------------------------

def test_back_adjustment_that_goes_negative_is_called_out():
    """Enough accumulated carry and the oldest prices go below zero."""
    front = _series(100, 10.0, step=0.0)
    nxt = _series(100, 500.0, start_index=80, step=0.0)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.BACK_ADJUSTED,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    assert float(out.bars.low.min()) > 0, "this direction adds, it does not subtract"
    # Now the other way round: a contract that fell hard between months, by
    # more than the old one was worth.
    front = _series(100, 100.0, step=0.0)
    nxt = _series(100, 0.5, start_index=80, step=0.0)
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.BACK_ADJUSTED,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    assert float(out.bars.low.min()) <= 0
    assert any("zero or below" in n for n in out.notes)


def test_the_series_records_how_it_was_made():
    front, nxt = _pair()
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=Adjustment.RATIO,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    assert out.bars.meta["continuous"] is True
    assert out.bars.meta["adjustment"] == "ratio"
    assert out.bars.meta["contracts"] == ["H", "M"]
    # The source names the splice, never one leg of it.
    assert out.bars.source == "continuous: H, M"
    assert len(out.bars.meta["rolls"]) == 1
    payload = out.to_dict()
    import json
    assert "rolls" in json.loads(json.dumps(payload, default=str))


@pytest.mark.parametrize("adjustment", list(Adjustment))
def test_every_adjustment_states_what_it_costs(adjustment):
    front, nxt = _pair()
    out = build_continuous([Contract("H", front), Contract("M", nxt)],
                           adjustment=adjustment,
                           rule=RollRule.DAYS_BEFORE_END, days_before_end=0)
    text = describe(out, "USD")
    assert "spliced from 2 contracts (H, M)" in text
    # Each one names the thing it is not safe for.
    assert any(w in text for w in ("meaningless", "not tradeable prices",
                                   "wrong by that much"))


def test_the_defaults_are_the_conventional_ones():
    assert DEFAULT_ROLL_DAYS == 7
    assert VOLUME_CONFIRM_BARS == 3
