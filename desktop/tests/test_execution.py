"""The cost model: spread, slippage and commission.

Costs are the part of a backtest most often got wrong in the flattering
direction, so every case here pins an exact number.
"""

from __future__ import annotations

import math

import pytest

from tradingbacktester.core.types import (CommissionMode, CostModel, Side,
                                          SlippageMode, SpreadMode)
from tradingbacktester.data.models import Instrument
from tradingbacktester.engine.execution import CostCalculator


@pytest.fixture
def instrument() -> Instrument:
    return Instrument(symbol="T", tick_size=0.01, point_value=1.0)


# --------------------------------------------------------------------------
# Spread
# --------------------------------------------------------------------------

def test_half_spread_is_charged_on_both_sides(instrument):
    """A buyer pays the ask, a seller receives the bid, entering and exiting."""
    calc = CostCalculator(
        CostModel(spread_mode=SpreadMode.HALF_EACH_SIDE, spread_points=0.10),
        instrument)
    assert calc.apply_entry(100.0, Side.LONG)[0] == pytest.approx(100.05)
    assert calc.apply_entry(100.0, Side.SHORT)[0] == pytest.approx(99.95)
    assert calc.apply_exit(100.0, Side.LONG)[0] == pytest.approx(99.95)
    assert calc.apply_exit(100.0, Side.SHORT)[0] == pytest.approx(100.05)


def test_full_spread_on_entry_is_charged_once(instrument):
    calc = CostCalculator(
        CostModel(spread_mode=SpreadMode.FULL_ON_ENTRY, spread_points=0.10),
        instrument)
    assert calc.apply_entry(100.0, Side.LONG)[0] == pytest.approx(100.10)
    assert calc.apply_exit(100.0, Side.LONG)[0] == pytest.approx(100.0)


def test_no_spread_leaves_the_price_alone(instrument):
    calc = CostCalculator(CostModel(), instrument)
    assert calc.apply_entry(100.0, Side.LONG)[0] == pytest.approx(100.0)
    assert calc.apply_exit(100.0, Side.SHORT)[0] == pytest.approx(100.0)


# --------------------------------------------------------------------------
# Slippage
# --------------------------------------------------------------------------

@pytest.mark.parametrize("side,is_entry,expected", [
    (Side.LONG, True, 100.25),      # buying to open: pay more
    (Side.SHORT, True, 99.75),      # selling to open: receive less
    (Side.LONG, False, 99.75),      # selling to close: receive less
    (Side.SHORT, False, 100.25),    # buying to close: pay more
])
def test_fixed_slippage_is_always_adverse(instrument, side, is_entry, expected):
    calc = CostCalculator(
        CostModel(slippage_mode=SlippageMode.FIXED_POINTS, slippage_value=0.25),
        instrument)
    fill = (calc.apply_entry(100.0, side) if is_entry
            else calc.apply_exit(100.0, side))[0]
    assert fill == pytest.approx(expected)


def test_percent_slippage(instrument):
    calc = CostCalculator(
        CostModel(slippage_mode=SlippageMode.PERCENT, slippage_value=0.1),
        instrument)
    assert calc.apply_entry(100.0, Side.LONG)[0] == pytest.approx(100.10)


def test_atr_slippage(instrument):
    calc = CostCalculator(
        CostModel(slippage_mode=SlippageMode.ATR_FRACTION, slippage_value=0.1),
        instrument)
    assert calc.apply_entry(100.0, Side.LONG, atr=2.0)[0] == pytest.approx(100.20)


def test_atr_slippage_with_no_atr_does_not_produce_nan(instrument):
    """During warm-up the ATR is undefined; a NaN fill price would poison
    every downstream number."""
    calc = CostCalculator(
        CostModel(slippage_mode=SlippageMode.ATR_FRACTION, slippage_value=0.1),
        instrument)
    fill = calc.apply_entry(100.0, Side.LONG, atr=float("nan"))[0]
    assert not math.isnan(fill)
    assert fill == pytest.approx(100.0)


# --------------------------------------------------------------------------
# Commission
# --------------------------------------------------------------------------

@pytest.mark.parametrize("mode,value,quantity,price,expected", [
    (CommissionMode.PER_UNIT, 0.5, 3.0, 100.0, 1.5),
    (CommissionMode.PER_TRADE, 2.0, 3.0, 100.0, 2.0),
    (CommissionMode.PERCENT_NOTIONAL, 0.1, 2.0, 100.0, 0.2),
])
def test_commission_modes(instrument, mode, value, quantity, price, expected):
    calc = CostCalculator(CostModel(commission_mode=mode, commission_value=value),
                          instrument)
    assert calc.commission(quantity, price) == pytest.approx(expected)


def test_minimum_commission_is_a_floor(instrument):
    calc = CostCalculator(
        CostModel(commission_mode=CommissionMode.PER_UNIT, commission_value=0.1,
                  min_commission=1.0), instrument)
    assert calc.commission(1.0, 100.0) == pytest.approx(1.0)
    assert calc.commission(50.0, 100.0) == pytest.approx(5.0)


def test_commission_is_never_negative(instrument):
    calc = CostCalculator(CostModel(), instrument)
    assert calc.commission(0.0, 100.0) >= 0.0
    assert calc.commission(10.0, 0.0) >= 0.0


def test_a_negative_cost_setting_is_refused():
    from tradingbacktester.core.errors import RiskError

    for bad in (CostModel(commission_value=-1.0),
                CostModel(spread_points=-1.0),
                CostModel(slippage_value=-1.0),
                CostModel(min_commission=-1.0)):
        with pytest.raises(RiskError):
            bad.validate()


def test_costs_and_spread_compose(instrument):
    """Both are adverse, so they add rather than cancel."""
    calc = CostCalculator(
        CostModel(spread_mode=SpreadMode.HALF_EACH_SIDE, spread_points=0.10,
                  slippage_mode=SlippageMode.FIXED_POINTS, slippage_value=0.25),
        instrument)
    assert calc.apply_entry(100.0, Side.LONG)[0] == pytest.approx(100.30)
    assert calc.apply_entry(100.0, Side.SHORT)[0] == pytest.approx(99.70)
