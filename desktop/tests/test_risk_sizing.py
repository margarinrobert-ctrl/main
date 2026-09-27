"""Position sizing.

Each case is chosen so the correct answer can be worked out in one line, which
is what makes a failure here diagnosable.
"""

from __future__ import annotations

import pytest

from tradingbacktester.core.types import AssetClass, RiskSettings, SizingMode
from tradingbacktester.data.models import Instrument
from tradingbacktester.engine.risk import PositionSizer


@pytest.fixture
def share() -> Instrument:
    """Point value 1, lot size 1: one unit is one share worth its price."""
    return Instrument(symbol="ACME", asset_class=AssetClass.EQUITY,
                      tick_size=0.01, point_value=1.0, lot_size=1.0)


@pytest.fixture
def future() -> Instrument:
    """Point value 20, like an E-mini Nasdaq contract."""
    return Instrument(symbol="NQ", asset_class=AssetClass.FUTURES,
                      tick_size=0.25, point_value=20.0, lot_size=1.0,
                      margin_per_unit=23_000.0)


def settings(**kwargs) -> RiskSettings:
    base = dict(starting_capital=100_000.0, sizing_mode=SizingMode.FIXED_UNITS)
    base.update(kwargs)
    return RiskSettings(**base)


# --------------------------------------------------------------------------
# The five modes
# --------------------------------------------------------------------------

def test_fixed_units(share):
    sizer = PositionSizer(settings(sizing_mode=SizingMode.FIXED_UNITS,
                                   fixed_units=7.0), share)
    assert sizer.size(100_000.0, 50.0) == pytest.approx(7.0)


def test_fixed_cash(share):
    """$10,000 of a $50 share is 200 shares."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.FIXED_CASH,
                                   fixed_cash=10_000.0), share)
    assert sizer.size(100_000.0, 50.0) == pytest.approx(200.0)


def test_percent_of_equity(share):
    """10% of 100,000 is 10,000; at $50 that is 200 shares."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.PERCENT_EQUITY,
                                   percent_equity=10.0), share)
    assert sizer.size(100_000.0, 50.0) == pytest.approx(200.0)


def test_risk_percent_uses_the_stop_distance(share):
    """1% of 100,000 is 1,000 at risk; a $2 stop distance buys 500 shares."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.RISK_PERCENT,
                                   risk_percent=1.0), share)
    assert sizer.size(100_000.0, 100.0, stop_price=98.0) == pytest.approx(500.0)


def test_risk_percent_accounts_for_point_value(future):
    """The same 2-point stop on NQ risks $40 per contract, not $2."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.RISK_PERCENT,
                                   risk_percent=1.0), future)
    # $1,000 at risk / (2 points x $20) = 25 contracts.
    assert sizer.size(100_000.0, 15_000.0, stop_price=14_998.0) == pytest.approx(25.0)


def test_risk_percent_falls_back_to_atr_without_a_stop(share):
    """No stop means no risk distance; the ATR stands in, and it is explained."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.RISK_PERCENT,
                                   risk_percent=1.0), share,
                          atr_stop_multiple=2.0)
    quantity = sizer.size(100_000.0, 100.0, stop_price=None, atr=1.0)
    assert quantity > 0
    assert sizer.last_reason


def test_volatility_target(share):
    """Size so one ATR of movement is the target percent of equity.

    1% of 100,000 is 1,000; with an ATR of 2.0 and point value 1 that is 500.
    """
    sizer = PositionSizer(settings(sizing_mode=SizingMode.VOLATILITY_TARGET,
                                   volatility_target_percent=1.0), share)
    assert sizer.size(100_000.0, 100.0, atr=2.0) == pytest.approx(500.0, rel=0.02)


# --------------------------------------------------------------------------
# Caps, rounding and refusal
# --------------------------------------------------------------------------

def test_max_position_units_caps_the_result(share):
    sizer = PositionSizer(settings(sizing_mode=SizingMode.PERCENT_EQUITY,
                                   percent_equity=100.0,
                                   max_position_units=10.0), share)
    assert sizer.size(100_000.0, 50.0) == pytest.approx(10.0)


def test_quantity_is_rounded_down_to_the_lot_size():
    fx = Instrument(symbol="EURUSD", asset_class=AssetClass.FOREX,
                    tick_size=0.00001, point_value=100_000.0, lot_size=0.01,
                    price_decimals=5)
    sizer = PositionSizer(settings(sizing_mode=SizingMode.FIXED_UNITS,
                                   fixed_units=0.037), fx)
    assert sizer.size(100_000.0, 1.1) == pytest.approx(0.03)


def test_a_size_below_one_lot_is_refused_with_a_reason(share):
    """Returning zero, not raising: the run continues and the log says why."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.FIXED_CASH,
                                   fixed_cash=10.0), share)
    assert sizer.size(100_000.0, 1000.0) == pytest.approx(0.0)
    assert sizer.last_reason


def test_zero_or_negative_equity_gives_no_position(share):
    sizer = PositionSizer(settings(sizing_mode=SizingMode.PERCENT_EQUITY,
                                   percent_equity=10.0), share)
    assert sizer.size(0.0, 50.0) == pytest.approx(0.0)
    assert sizer.size(-500.0, 50.0) == pytest.approx(0.0)


def test_zero_price_does_not_divide_by_zero(share):
    sizer = PositionSizer(settings(sizing_mode=SizingMode.FIXED_CASH,
                                   fixed_cash=10_000.0), share)
    assert sizer.size(100_000.0, 0.0) == pytest.approx(0.0)


def test_a_stop_at_the_entry_price_does_not_divide_by_zero(share):
    sizer = PositionSizer(settings(sizing_mode=SizingMode.RISK_PERCENT,
                                   risk_percent=1.0), share)
    quantity = sizer.size(100_000.0, 100.0, stop_price=100.0, atr=float("nan"))
    assert quantity == pytest.approx(0.0)
    assert sizer.last_reason


def test_size_is_never_negative(share):
    for mode in SizingMode:
        sizer = PositionSizer(settings(sizing_mode=mode), share)
        assert sizer.size(100_000.0, 100.0, stop_price=99.0, atr=1.0) >= 0.0


# --------------------------------------------------------------------------
# Margin
# --------------------------------------------------------------------------

def test_margin_per_unit_limits_the_size(future):
    """$100,000 of equity buys four NQ contracts at $23,000 initial margin."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.FIXED_UNITS,
                                   fixed_units=10.0, use_margin=True,
                                   margin_per_unit=23_000.0), future)
    assert sizer.size(100_000.0, 15_000.0, free_equity=100_000.0) <= 4.0


def test_margin_percent_limits_the_size(share):
    """50% initial margin doubles the buying power, and no further."""
    sizer = PositionSizer(settings(sizing_mode=SizingMode.PERCENT_EQUITY,
                                   percent_equity=400.0, use_margin=True,
                                   margin_percent=50.0), share)
    quantity = sizer.size(100_000.0, 100.0, free_equity=100_000.0)
    # 100,000 of margin at 50% supports 200,000 notional = 2,000 shares.
    assert quantity <= 2000.0 + 1e-6


def test_no_free_equity_means_no_position(future):
    sizer = PositionSizer(settings(sizing_mode=SizingMode.FIXED_UNITS,
                                   fixed_units=1.0, use_margin=True,
                                   margin_per_unit=23_000.0), future)
    assert sizer.size(100_000.0, 15_000.0, free_equity=100.0) == pytest.approx(0.0)
    assert sizer.last_reason
